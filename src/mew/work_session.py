import difflib
import json
import hashlib
from pathlib import Path
import re
import shlex

from .cli_command import mew_command, mew_executable
from .read_tools import (
    DEFAULT_READ_MAX_CHARS,
    glob_paths,
    inspect_dir,
    is_sensitive_path,
    read_file,
    resolve_allowed_path,
    search_text,
    summarize_read_result,
)
from .state import next_id
from .tasks import clip_output, find_task
from .test_discovery import convention_test_path_for_mew_source, discover_tests_for_source
from .timeutil import now_iso, parse_time
from .toolbox import format_command_record, run_command_record, run_command_record_streaming, run_git_tool
from .typed_memory import FileMemoryBackend, entry_to_dict
from .patch_draft import PATCH_BLOCKER_RECOVERY_ACTIONS
from .write_tools import (
    build_write_intent,
    classify_write_intent_world_state,
    edit_file,
    edit_file_hunks,
    restore_write_snapshot,
    snapshot_write_path,
    summarize_write_result,
    write_file,
)


WORK_SESSION_STATUSES = {"active", "closed"}
WORK_TOOL_STATUSES = {"running", "completed", "failed", "interrupted"}
WORK_MODEL_TURN_STATUSES = {"running", "completed", "failed", "interrupted"}
WORK_TODO_STATUSES = {
    "drafting",
    "blocked_on_patch",
    "awaiting_review",
    "awaiting_approval",
    "applying",
    "verifying",
    "completed",
}
WORK_TODO_PHASE_STATUSES = {"drafting", "blocked_on_patch"}
_TINY_WRITE_READY_DRAFT_BLOCKER_UNKNOWN_RECOVERY_ACTION = "refresh_cached_window"
_TINY_WRITE_READY_DRAFT_BLOCKER_REASON_PREFIX = "write-ready tiny draft blocker:"
_RESUME_DRAFT_FROM_CACHED_WINDOWS_ACTION = "resume_draft_from_cached_windows"


def _tiny_write_ready_draft_recovery_action(blocker_code):
    code = str(blocker_code or "").strip()
    return PATCH_BLOCKER_RECOVERY_ACTIONS.get(
        code,
        _TINY_WRITE_READY_DRAFT_BLOCKER_UNKNOWN_RECOVERY_ACTION,
    )


def _tiny_write_ready_draft_turn_todo_id(*, decision_plan=None, action_plan=None, action=None):
    action_plan = action_plan if isinstance(action_plan, dict) else {}
    decision_plan = decision_plan if isinstance(decision_plan, dict) else {}
    action = action if isinstance(action, dict) else {}
    for candidate in (action_plan, action, decision_plan):
        candidate_todo_id = str(candidate.get("todo_id") or "").strip()
        if not candidate_todo_id:
            blocker = candidate.get("blocker")
            if isinstance(blocker, dict):
                candidate_todo_id = str(blocker.get("todo_id") or "").strip()
        if candidate_todo_id:
            return candidate_todo_id
    return ""


def _tiny_write_ready_draft_blocker_from_turn(
    *, decision_plan=None, action_plan=None, action=None
):
    decision_plan = decision_plan if isinstance(decision_plan, dict) else {}
    action_plan = action_plan if isinstance(action_plan, dict) else {}
    action = action if isinstance(action, dict) else {}
    structured_blocker = {}
    for candidate in (
        action_plan.get("blocker"),
        action.get("blocker"),
        decision_plan.get("blocker"),
    ):
        if isinstance(candidate, dict):
            structured_blocker = candidate
            break
    reason = str(action.get("reason") or "").strip()
    if structured_blocker:
        code = str(structured_blocker.get("code") or "").strip()
    elif reason.startswith(_TINY_WRITE_READY_DRAFT_BLOCKER_REASON_PREFIX):
        code = reason[len(_TINY_WRITE_READY_DRAFT_BLOCKER_REASON_PREFIX) :].strip()
    else:
        code = str(decision_plan.get("code") or "").strip()
    detail = str(
        (structured_blocker.get("detail") if structured_blocker else None)
        or decision_plan.get("detail")
        or action_plan.get("summary")
        or action.get("reason")
        or ""
    ).strip()
    blocker = {
        "code": code,
        "detail": detail,
        "recovery_action": _tiny_write_ready_draft_recovery_action(code),
    }
    path = str(
        (structured_blocker.get("path") if structured_blocker else None)
        or decision_plan.get("path")
        or ""
    ).strip()
    if path:
        blocker["path"] = path
    line_start = structured_blocker.get("line_start") if structured_blocker else decision_plan.get("line_start")
    line_end = structured_blocker.get("line_end") if structured_blocker else decision_plan.get("line_end")
    try:
        line_start = int(line_start)
        if line_start > 0:
            blocker["line_start"] = line_start
    except (TypeError, ValueError):
        pass
    try:
        line_end = int(line_end)
        if line_end > 0:
            blocker["line_end"] = line_end
    except (TypeError, ValueError):
        pass
    return blocker


def _coerce_non_negative_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _latest_tiny_write_ready_draft_turn(model_turns, *, todo_id=None):
    todo_id = str(todo_id or "").strip()
    for turn in reversed(list(model_turns or [])):
        if str(turn.get("status") or "") != "completed":
            continue
        metrics = turn.get("model_metrics") or {}
        outcome = str(metrics.get("tiny_write_ready_draft_outcome") or "").strip()
        if outcome not in {"blocker", "succeeded"}:
            continue
        if todo_id and _tiny_write_ready_draft_turn_todo_id(
            decision_plan=turn.get("decision_plan"),
            action_plan=turn.get("action_plan"),
            action=turn.get("action"),
        ) != todo_id:
            continue
        return turn
    return {}


def _tiny_write_ready_draft_turn_matches_todo(turn, *, todo_id):
    expected_todo_id = str(todo_id or "").strip()
    if not expected_todo_id:
        return False
    return (
        _tiny_write_ready_draft_turn_todo_id(
            decision_plan=turn.get("decision_plan"),
            action_plan=turn.get("action_plan"),
            action=turn.get("action"),
        )
        == expected_todo_id
    )


def _apply_tiny_write_ready_draft_outcome_to_active_work_todo(
    todo,
    *,
    turn,
    current_time=None,
    todo_id=None,
):
    turn = turn if isinstance(turn, dict) else {}
    todo = todo if isinstance(todo, dict) else {}
    if not todo:
        return todo
    metrics = turn.get("model_metrics") or {}
    outcome = str(metrics.get("tiny_write_ready_draft_outcome") or "").strip()
    if outcome not in {"blocker", "succeeded"}:
        return todo
    if not _tiny_write_ready_draft_turn_matches_todo(
        turn,
        todo_id=todo_id if todo_id is not None else todo.get("id"),
    ):
        return todo
    attempts = todo.get("attempts") if isinstance(todo.get("attempts"), dict) else {}
    draft_attempts = _coerce_non_negative_int(attempts.get("draft"), 0)
    review_attempts = _coerce_non_negative_int(attempts.get("review"), 0)
    observed_draft_attempts = _coerce_non_negative_int(metrics.get("draft_attempts"), 0)
    old_status = str(todo.get("status") or "").strip()
    decision_plan = turn.get("decision_plan") or {}
    action_plan = turn.get("action_plan") or {}
    action = turn.get("action") or {}
    if observed_draft_attempts > draft_attempts:
        draft_attempts = observed_draft_attempts
    elif observed_draft_attempts == 0 and old_status != "blocked_on_patch" and outcome == "blocker":
        draft_attempts += 1
    if outcome == "blocker":
        todo["status"] = "blocked_on_patch"
        todo["blocker"] = _tiny_write_ready_draft_blocker_from_turn(
            decision_plan=decision_plan,
            action_plan=action_plan,
            action=action,
        )
    else:
        todo["status"] = "drafting"
        todo["blocker"] = {}
    todo["attempts"] = {"draft": draft_attempts, "review": review_attempts}
    todo["updated_at"] = current_time or now_iso()
    return todo

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
    "edit_file_hunks",
}
APPROVAL_WAIT_RE = re.compile(
    r"\b(?:wait|waiting|await|awaiting)\b.*\b(?:approval|approve|rejection|reject)\b"
    r"|\b(?:approval|approve|rejection|reject)\b.*\b(?:wait|waiting|await|awaiting)\b",
    re.IGNORECASE,
)
READ_ONLY_WORK_TOOLS = {"inspect_dir", "read_file", "search_text", "glob"}
GIT_WORK_TOOLS = {"git_status", "git_diff", "git_log"}
COMMAND_WORK_TOOLS = {"run_command", "run_tests"} | GIT_WORK_TOOLS
WRITE_WORK_TOOLS = {"write_file", "edit_file", "edit_file_hunks"}
SHELL_CHAIN_OPERATORS = {"&&", "||", ";", "|", "&"}
APPROVAL_STATUS_INDETERMINATE = "indeterminate"
NON_PENDING_APPROVAL_STATUSES = {"applying", "applied", "rejected", APPROVAL_STATUS_INDETERMINATE}
RESOLVED_APPROVAL_MEMORY_STATUSES = {"applied", "rejected", APPROVAL_STATUS_INDETERMINATE}
RECOVERY_PLAN_ACTION_PRIORITY = (
    "needs_user_review",
    "verify_completed_write",
    "retry_apply_write",
    "retry_tool",
    "retry_dry_run_write",
    "retry_verification",
    "resume_draft_from_cached_windows",
    "replan",
)
WORK_RECOVERY_EFFECT_PRIORITY = (
    "rollback_needed",
    "verify_pending",
    "write_started",
    "completed_externally",
    "not_started",
    "partial",
    "target_diverged",
    "action_committed",
    "no_action",
    "unknown",
)
WORK_RECOVERY_EFFECT_CLASSES = {
    "no_action",
    "action_committed",
    "write_started",
    "verify_pending",
    "rollback_needed",
    "completed_externally",
    "not_started",
    "partial",
    "target_diverged",
    "unknown",
}
DEFAULT_DIFF_PREVIEW_MAX_CHARS = 1600
DEFAULT_RESUME_APPROVAL_DIFF_MAX_CHARS = 50_000
DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS = 500
DEFAULT_RUNNING_OUTPUT_MAX_CHARS = 4_000
DEFAULT_RESUME_USER_PREFERENCES_LIMIT = 5
DEFAULT_RESUME_USER_PREFERENCE_MAX_CHARS = 300
DEFAULT_ACTIVE_MEMORY_LIMIT = 6
DEFAULT_ACTIVE_MEMORY_TEXT_MAX_CHARS = 700
WORK_REPEAT_CONSECUTIVE_LIMIT = 2
WORK_REPEAT_TOTAL_LIMIT = 4
WORK_SESSION_STEP_BUDGET = 30
WORK_SESSION_NEAR_STEP_RATIO = 0.8
WORK_SESSION_WALL_NEAR_SECONDS = 60 * 60
WORK_SESSION_WALL_HIGH_SECONDS = 3 * 60 * 60
WORK_SESSION_FAILURE_NEAR_COUNT = 2
WORK_SESSION_FAILURE_HIGH_COUNT = 4
WORK_REPEAT_SIGNATURE_IGNORED_FIELDS = {
    "reason",
    "summary",
    "text",
    "note",
    "question",
    "message_type",
    "completion_summary",
}
WORK_ACTION_DISPLAY_FIELDS = (
    "path",
    "query",
    "pattern",
    "command",
    "cwd",
    "base",
    "limit",
    "offset",
    "line_start",
    "line_count",
    "apply",
    "create",
    "replace_all",
    "staged",
    "stat",
)
ACTIVE_MEMORY_ALWAYS_TYPES = {"user"}
ACTIVE_MEMORY_RELEVANT_TYPES = {"feedback", "project", "reference", "unknown"}
ACTIVE_MEMORY_STOP_WORDS = {
    "about",
    "after",
    "and",
    "are",
    "before",
    "build",
    "but",
    "calling",
    "can",
    "coding",
    "code",
    "change",
    "commits",
    "completed",
    "constraints",
    "covered",
    "current",
    "documentation",
    "done",
    "exercise",
    "focus",
    "for",
    "from",
    "git",
    "has",
    "have",
    "improve",
    "improvement",
    "into",
    "itself",
    "keep",
    "mew",
    "not",
    "one",
    "our",
    "out",
    "pick",
    "recently",
    "repeat",
    "reviewable",
    "run",
    "same",
    "session",
    "should",
    "small",
    "topics",
    "task",
    "that",
    "this",
    "the",
    "then",
    "through",
    "use",
    "was",
    "were",
    "whether",
    "will",
    "with",
    "work",
    "you",
    "your",
}
ACTIVE_MEMORY_DESCRIPTION_CUTOFFS = (
    "\n\nRecently completed git commits",
    "\n\nCurrent coding focus:",
    "\n\nActive work sessions",
    "\n\nTasks",
    "\n\nConstraints:",
)
ACTIVE_MEMORY_TERM_RE = re.compile(r"[a-z0-9_][a-z0-9_-]{2,}")
ACTIVE_MEMORY_NEGATED_PHRASE_RE = re.compile(
    r"\b(?:not|without|except)\s+("
    r"[a-z0-9_][a-z0-9_-]{2,}"
    r"(?:\s+[a-z0-9_][a-z0-9_-]{2,}){0,2}"
    r")"
)
PLAN_ITEM_EXACT_READ_WINDOW_RE = re.compile(
    r"^(?:read(?:/cache)?|cache)\s+([^\s:]+):(\d+)-(\d+)\b",
    re.IGNORECASE,
)


def diff_line_counts(diff):
    added = 0
    removed = 0
    for line in (diff or "").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {"added": added, "removed": removed}


def clip_inline_text(text, limit=240):
    text = " ".join(str(text or "").split())
    if not text or len(text) <= limit:
        return text
    marker = " ... output truncated ..."
    prefix_limit = max(1, limit - len(marker))
    prefix = text[:prefix_limit].rstrip()
    boundary = prefix.rfind(" ")
    if boundary >= max(20, prefix_limit // 2):
        prefix = prefix[:boundary].rstrip()
    return f"{prefix}{marker}"


def latest_unresolved_failure(failures):
    for failure in reversed(failures or []):
        if failure.get("recovery_status") == "superseded":
            continue
        return failure
    return {}


def format_work_failure_risk(failure, max_chars=260):
    if not failure:
        return ""
    tool = failure.get("tool") or "tool"
    tool_id = failure.get("tool_call_id")
    tool_ref = f"{tool}#{tool_id}" if tool_id is not None else tool
    exit_text = f" exit={failure.get('exit_code')}" if failure.get("exit_code") is not None else ""
    summary = failure.get("error") or failure.get("summary") or "failed"
    return f"{tool_ref} failed{exit_text}: {clip_inline_text(summary, max_chars)}"


def _result_diff_stats(result, diff):
    stats = (result or {}).get("diff_stats")
    if isinstance(stats, dict) and "added" in stats and "removed" in stats:
        return {"added": stats.get("added") or 0, "removed": stats.get("removed") or 0}
    return diff_line_counts(diff)


def format_diff_preview(diff, max_chars=DEFAULT_DIFF_PREVIEW_MAX_CHARS, diff_stats=None):
    if not diff:
        return ""
    counts = diff_stats if diff_stats is not None else diff_line_counts(diff)
    return (
        f"Diff preview (+{counts['added']} -{counts['removed']})\n"
        f"{clip_output(diff, max_chars)}"
    )


def _planned_write_preview_lines(text):
    text = str(text or "")
    if not text:
        return []
    return text.splitlines()


def _planned_write_preview_diff(path, before_text, after_text):
    before_lines = _planned_write_preview_lines(before_text)
    after_lines = _planned_write_preview_lines(after_text)
    if before_lines == after_lines:
        return ""
    return "\n".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=path or "before",
            tofile=path or "after",
            lineterm="",
        )
    )


def format_work_batch_write_preview(tool, max_chars=400):
    tool = dict(tool or {})
    tool_type = tool.get("type") or tool.get("tool") or ""
    if tool_type not in WRITE_WORK_TOOLS:
        return ""
    if tool.get("apply"):
        return ""
    path = tool.get("path") or ""
    diff = ""
    if tool_type == "write_file":
        diff = _planned_write_preview_diff(path, "", tool.get("content") or "")
    elif tool_type == "edit_file":
        diff = _planned_write_preview_diff(path, tool.get("old") or "", tool.get("new") or "")
    elif tool_type == "edit_file_hunks":
        parts = []
        edits = tool.get("edits") or []
        for index, edit in enumerate(edits, start=1):
            item = edit if isinstance(edit, dict) else {}
            hunk_diff = _planned_write_preview_diff(path, item.get("old") or "", item.get("new") or "")
            if not hunk_diff:
                continue
            if len(edits) > 1:
                parts.append(f"@@ planned hunk {index} @@")
            parts.append(hunk_diff)
        diff = "\n".join(parts)
    if not diff:
        return ""
    return format_diff_preview(diff, max_chars=max_chars)


def clipped_approval_diff(diff, max_chars=DEFAULT_RESUME_APPROVAL_DIFF_MAX_CHARS):
    diff = str(diff or "")
    if len(diff) <= max_chars:
        return diff, False
    marker = "\n... output truncated ..."
    prefix_limit = max(0, max_chars - len(marker))
    return diff[:prefix_limit] + marker, True


def build_work_user_preferences(state, limit=DEFAULT_RESUME_USER_PREFERENCES_LIMIT):
    memory = (state or {}).get("memory") if isinstance(state, dict) else {}
    deep = (memory or {}).get("deep") if isinstance(memory, dict) else {}
    preferences = (deep or {}).get("preferences") if isinstance(deep, dict) else []
    if not isinstance(preferences, list):
        preferences = []
    preferences = [str(item or "").strip() for item in preferences if str(item or "").strip()]
    total = len(preferences)
    visible_limit = min(DEFAULT_RESUME_USER_PREFERENCES_LIMIT, max(1, int(limit or DEFAULT_RESUME_USER_PREFERENCES_LIMIT)))
    visible = [
        clip_output(item, DEFAULT_RESUME_USER_PREFERENCE_MAX_CHARS)
        for item in preferences[-visible_limit:]
    ]
    return {
        "source": "memory.deep.preferences",
        "items": visible,
        "total": total,
        "truncated": total > len(visible),
    }


def active_memory_source_text(value):
    text = str(value or "")
    earliest = len(text)
    for marker in ACTIVE_MEMORY_DESCRIPTION_CUTOFFS:
        index = text.find(marker)
        if index >= 0:
            earliest = min(earliest, index)
    return text[:earliest]


def active_memory_negated_terms(text):
    negated = set()
    for match in ACTIVE_MEMORY_NEGATED_PHRASE_RE.finditer(text):
        for term in ACTIVE_MEMORY_TERM_RE.findall(match.group(1)):
            if term not in ACTIVE_MEMORY_STOP_WORDS:
                negated.add(term)
    return negated


def active_memory_terms(session=None, task=None):
    parts = []
    for source in (task or {}, session or {}):
        if not isinstance(source, dict):
            continue
        for key in ("title", "description", "kind", "goal"):
            value = source.get(key)
            if value:
                parts.append(active_memory_source_text(value) if key in ("description", "goal") else str(value))
    text = " ".join(parts).casefold()
    negated = active_memory_negated_terms(text)
    terms = []
    for term in ACTIVE_MEMORY_TERM_RE.findall(text):
        if term in ACTIVE_MEMORY_STOP_WORDS or term in negated or term in terms:
            continue
        terms.append(term)
    return terms[:20]


def active_memory_match(entry, terms):
    haystack = " ".join(
        [
            entry.name,
            entry.description,
            entry.body,
            entry.memory_type,
            entry.scope,
        ]
    ).casefold()
    matched_terms = [term for term in terms if term in haystack]
    if entry.memory_type in ACTIVE_MEMORY_ALWAYS_TYPES:
        score = 100 + len(matched_terms)
    elif entry.memory_type in ACTIVE_MEMORY_RELEVANT_TYPES and matched_terms:
        score = 10 + len(matched_terms)
    else:
        return None
    reason = "always_include_user_memory" if entry.memory_type in ACTIVE_MEMORY_ALWAYS_TYPES else "matched_task_terms"
    return {
        "score": score,
        "reason": reason,
        "matched_terms": matched_terms[:8],
    }


def plan_item_exact_read_window(plan_item):
    text = str(plan_item or "").strip()
    if not text:
        return {}
    match = PLAN_ITEM_EXACT_READ_WINDOW_RE.match(text)
    if not match:
        return {}
    try:
        line_start = int(match.group(2))
        line_end = int(match.group(3))
    except (TypeError, ValueError):
        return {}
    if line_start <= 0 or line_end <= 0:
        return {}
    if line_end < line_start:
        line_start, line_end = line_end, line_start
    return {
        "path": match.group(1),
        "line_start": line_start,
        "line_end": line_end,
    }


def cached_window_covers_exact_read(cached_window, requested_window):
    cached_window = cached_window if isinstance(cached_window, dict) else {}
    requested_window = requested_window if isinstance(requested_window, dict) else {}
    if not requested_window:
        return False
    cached_path = str(cached_window.get("path") or "").strip()
    requested_path = str(requested_window.get("path") or "").strip()
    if not cached_path or not requested_path:
        return False
    if cached_path != requested_path and not cached_path.endswith(requested_path):
        return False
    try:
        cached_start = int(cached_window.get("line_start") or 0)
        cached_end = int(cached_window.get("line_end") or 0)
        requested_start = int(requested_window.get("line_start") or 0)
        requested_end = int(requested_window.get("line_end") or 0)
    except (TypeError, ValueError):
        return False
    return cached_start <= requested_start and cached_end >= requested_end


def first_actionable_plan_item(plan_items, cached_windows):
    items = [str(item or "").strip() for item in (plan_items or []) if str(item or "").strip()]
    cached_windows = list(cached_windows or [])
    skipped = []
    for item in items:
        requested_window = plan_item_exact_read_window(item)
        if not requested_window:
            return item, skipped
        if any(cached_window_covers_exact_read(cached_window, requested_window) for cached_window in cached_windows):
            skipped.append(
                {
                    "plan_item": item,
                    "requested_window": requested_window,
                    "reason": (
                        "exact read window already cached; skip this leading read/cache plan item "
                        "and evaluate the next actionable item"
                    ),
                }
            )
            continue
        return item, skipped
    return "", skipped


def revise_active_memory_item(item, *, base_dir="."):
    item = dict(item or {})
    if item.get("memory_kind") != "file-pair":
        return item, None
    source_path = str(item.get("source_path") or "").strip()
    test_path = str(item.get("test_path") or "").strip()
    missing_paths = []
    for path in (source_path, test_path):
        if not path:
            missing_paths.append(path)
            continue
        if not (Path(base_dir) / path).exists():
            missing_paths.append(path)
    if missing_paths:
        return None, {
            "id": item.get("id"),
            "memory_kind": item.get("memory_kind"),
            "name": item.get("name") or item.get("key") or "memory",
            "source_path": source_path,
            "test_path": test_path,
            "drop_reason": "precondition_miss",
            "missing_paths": missing_paths,
        }
    item["revise_status"] = "kept"
    return item, None


def build_work_active_memory(session=None, task=None, limit=DEFAULT_ACTIVE_MEMORY_LIMIT, base_dir="."):
    limit = max(0, int(limit or 0))
    terms = active_memory_terms(session=session, task=task)
    result = {
        "source": ".mew/memory",
        "terms": terms,
        "items": [],
        "total": 0,
        "truncated": False,
    }
    if limit <= 0:
        return result
    try:
        entries = FileMemoryBackend(base_dir).entries()
    except OSError:
        entries = []
    scored = []
    dropped = []
    for entry in entries:
        match = active_memory_match(entry, terms)
        if not match:
            continue
        item = entry_to_dict(entry)
        item["score"] = match["score"]
        item["reason"] = match["reason"]
        item["matched_terms"] = match["matched_terms"]
        item["text"] = clip_output(item.get("text") or "", DEFAULT_ACTIVE_MEMORY_TEXT_MAX_CHARS)
        item, dropped_item = revise_active_memory_item(item, base_dir=base_dir)
        if dropped_item:
            dropped.append(dropped_item)
            continue
        scored.append(item)
    scored.sort(key=lambda item: (item.get("score") or 0, item.get("created_at") or ""), reverse=True)
    result["total"] = len(scored)
    result["items"] = scored[:limit]
    result["truncated"] = len(scored) > len(result["items"])
    if dropped:
        result["dropped_items"] = dropped[:limit]
    return result


def active_work_session(state):
    for session in reversed(state.get("work_sessions", [])):
        task = work_session_task(state, session)
        if session.get("status") == "active" and (not task or task.get("status") != "done"):
            return session
    return None


def active_memory_item_detail_parts(item, include_score=False, include_matches=False):
    details = [item.get("reason") or "recalled"]
    if item.get("created_at"):
        details.append(f"created_at={item.get('created_at')}")
    if include_score and item.get("score") is not None:
        details.append(f"score={item.get('score')}")
    if include_matches:
        matched = ", ".join(str(term) for term in item.get("matched_terms") or [])
        if matched:
            details.append(f"matched={matched}")
    return details


def active_work_sessions(state):
    sessions = []
    for session in state.get("work_sessions", []):
        task = work_session_task(state, session)
        if session.get("status") == "active" and (not task or task.get("status") != "done"):
            sessions.append(session)
    return sessions


def work_session_for_task(state, task_id):
    wanted = str(task_id)
    for session in reversed(state.get("work_sessions", [])):
        task = work_session_task(state, session)
        if (
            str(session.get("task_id")) == wanted
            and session.get("status") == "active"
            and (not task or task.get("status") != "done")
        ):
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


def _canonical_work_parameter(value):
    if isinstance(value, dict):
        return {str(key): _canonical_work_parameter(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_work_parameter(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float, str)):
        return value
    return str(value)


def _int_work_parameter(parameters, key, default):
    try:
        return int(parameters.get(key) if parameters.get(key) is not None else default)
    except (TypeError, ValueError):
        return default


def _clamped_int_work_parameter(parameters, key, default, minimum, maximum):
    return max(minimum, min(_int_work_parameter(parameters, key, default), maximum))


def _float_work_parameter(parameters, key, default):
    try:
        return float(parameters.get(key) if parameters.get(key) is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _optional_int_work_parameter(parameters, key):
    if parameters.get(key) is None:
        return None
    try:
        return int(parameters.get(key))
    except (TypeError, ValueError):
        return None


def _optional_clamped_int_work_parameter(parameters, key, minimum, maximum):
    value = _optional_int_work_parameter(parameters, key)
    if value is None:
        return None
    return max(minimum, min(value, maximum))


def work_tool_signature(tool, parameters):
    tool = tool or ""
    parameters = dict(parameters or {})
    if tool == "inspect_dir":
        parameters = {"path": parameters.get("path") or ".", "limit": _clamped_int_work_parameter(parameters, "limit", 50, 1, 200)}
    elif tool == "read_file":
        line_start = _optional_clamped_int_work_parameter(parameters, "line_start", 1, 1_000_000)
        normalized = {
            "path": parameters.get("path") or "",
            "max_chars": _clamped_int_work_parameter(parameters, "max_chars", DEFAULT_READ_MAX_CHARS, 1, 50_000),
        }
        if line_start is not None:
            normalized["line_start"] = line_start
            normalized["line_count"] = _clamped_int_work_parameter(parameters, "line_count", 120, 1, 1000)
        else:
            normalized["offset"] = _clamped_int_work_parameter(parameters, "offset", 0, 0, 1_000_000)
        parameters = normalized
    elif tool == "search_text":
        parameters = {
            "query": parameters.get("query") or "",
            "path": parameters.get("path") or ".",
            "pattern": parameters.get("pattern") or "",
            "max_matches": _clamped_int_work_parameter(parameters, "max_matches", 50, 1, 200),
            "context_lines": _clamped_int_work_parameter(parameters, "context_lines", 3, 0, 5),
        }
    elif tool == "glob":
        parameters = {
            "pattern": parameters.get("pattern") or "",
            "path": parameters.get("path") or ".",
            "max_matches": _clamped_int_work_parameter(parameters, "max_matches", 100, 1, 500),
        }
    elif tool == "git_status":
        parameters = {"cwd": parameters.get("cwd") or "."}
    elif tool == "git_diff":
        parameters = {
            "cwd": parameters.get("cwd") or ".",
            "staged": bool(parameters.get("staged")),
            "stat": bool(parameters.get("stat")),
            "base": parameters.get("base") or "",
        }
    elif tool == "git_log":
        parameters = {"cwd": parameters.get("cwd") or ".", "limit": _clamped_int_work_parameter(parameters, "limit", 20, 1, 100)}
    elif tool in ("run_command", "run_tests"):
        parameters = {
            "command": parameters.get("command") or "",
            "cwd": parameters.get("cwd") or ".",
            "timeout": _float_work_parameter(parameters, "timeout", 300),
        }
    elif tool == "write_file":
        apply = bool(parameters.get("apply"))
        normalized = {
            "path": parameters.get("path") or "",
            "content": parameters.get("content") or "",
            "create": bool(parameters.get("create")),
            "apply": apply,
        }
        if apply:
            normalized.update(
                {
                    "verify_command": parameters.get("verify_command") or "",
                    "verify_cwd": parameters.get("verify_cwd") or ".",
                    "verify_timeout": _float_work_parameter(parameters, "verify_timeout", 300),
                }
            )
        parameters = normalized
    elif tool == "edit_file":
        apply = bool(parameters.get("apply"))
        normalized = {
            "path": parameters.get("path") or "",
            "old": parameters.get("old") or "",
            "new": parameters.get("new") or "",
            "replace_all": bool(parameters.get("replace_all")),
            "apply": apply,
        }
        if apply:
            normalized.update(
                {
                    "verify_command": parameters.get("verify_command") or "",
                    "verify_cwd": parameters.get("verify_cwd") or ".",
                    "verify_timeout": _float_work_parameter(parameters, "verify_timeout", 300),
                }
            )
        parameters = normalized
    elif tool == "edit_file_hunks":
        apply = bool(parameters.get("apply"))
        edits = []
        for item in parameters.get("edits") or []:
            if not isinstance(item, dict):
                continue
            edits.append(
                {
                    "old": item.get("old") or "",
                    "new": item.get("new") or "",
                }
            )
        normalized = {
            "path": parameters.get("path") or "",
            "edits": edits,
            "apply": apply,
        }
        if apply:
            normalized.update(
                {
                    "verify_command": parameters.get("verify_command") or "",
                    "verify_cwd": parameters.get("verify_cwd") or ".",
                    "verify_timeout": _float_work_parameter(parameters, "verify_timeout", 300),
                }
            )
        parameters = normalized
    else:
        parameters = {
            key: value
            for key, value in parameters.items()
            if key not in WORK_REPEAT_SIGNATURE_IGNORED_FIELDS
        }
    return {
        "tool": tool,
        "parameters": _canonical_work_parameter(parameters),
    }


def work_tool_repeat_guard(
    session,
    tool,
    parameters,
    *,
    consecutive_limit=WORK_REPEAT_CONSECUTIVE_LIMIT,
    total_limit=WORK_REPEAT_TOTAL_LIMIT,
):
    if not isinstance(session, dict):
        return {}
    signature = work_tool_signature(tool, parameters)
    consecutive = 0
    counting_consecutive = True
    total = 0
    matching_ids = []
    for call in reversed(session.get("tool_calls") or []):
        if not isinstance(call, dict):
            continue
        call_signature = work_tool_signature(call.get("tool"), call.get("parameters") or {})
        is_match = call_signature == signature
        if is_match:
            total += 1
            matching_ids.append(call.get("id"))
            if counting_consecutive:
                consecutive += 1
        elif counting_consecutive:
            counting_consecutive = False
    if consecutive < consecutive_limit and total < total_limit:
        return {}
    reason = "consecutive_repeat" if consecutive >= consecutive_limit else "total_repeat"
    count = consecutive if reason == "consecutive_repeat" else total
    message = (
        f"repeat-action guard blocked {tool}: identical parameters were used "
        f"{count} previous time(s); review the prior result, incorporate any prior rejection or review feedback, change parameters, "
        "summarize what is missing, or ask the user before retrying"
    )
    return {
        "reason": reason,
        "tool": tool,
        "signature": signature,
        "consecutive_count": consecutive,
        "total_count": total,
        "matching_tool_call_ids": list(reversed(matching_ids[:10])),
        "message": message,
        "suggested_next": "review prior result, change parameters, summarize the blocker, or ask the user",
    }


def _read_file_is_broad(parameters):
    parameters = dict(parameters or {})
    if _optional_clamped_int_work_parameter(parameters, "line_start", 1, 1_000_000) is not None:
        return False
    offset = _optional_clamped_int_work_parameter(parameters, "offset", 0, 1_000_000)
    return offset in (None, 0)


def broad_read_after_search_miss_guard(session, tool, parameters, *, task=None):
    if not isinstance(session, dict) or tool != "read_file":
        return {}
    parameters = dict(parameters or {})
    if not _read_file_is_broad(parameters):
        return {}
    path = _working_memory_target_path_text(parameters.get("path"))
    if not path:
        return {}
    calls = list(session.get("tool_calls") or [])
    memory = build_working_memory(session.get("model_turns") or [], calls, task=task)
    target_paths = _coerce_working_memory_target_paths(memory.get("target_paths") or [])
    if path not in target_paths:
        return {}

    latest_search = None
    for call in reversed(calls):
        if not isinstance(call, dict) or call.get("tool") != "search_text" or call.get("status") != "completed":
            continue
        if _working_memory_target_path_text(work_call_path(call)) != path:
            continue
        latest_search = call
        break
    if not latest_search:
        return {}
    search_result = latest_search.get("result") or {}
    if search_result.get("matches"):
        return {}

    latest_window = None
    for call in reversed(calls):
        if not isinstance(call, dict) or call.get("tool") != "read_file" or call.get("status") != "completed":
            continue
        if _working_memory_target_path_text(work_call_path(call)) != path:
            continue
        latest_window = _read_file_call_line_window(call)
        if latest_window is not None:
            break

    query = search_result.get("query") or (latest_search.get("parameters") or {}).get("query") or ""
    if latest_window is not None:
        line_start, line_end = latest_window
        suggested_next = f"read_file path={path} line_start={line_start} line_count={line_end - line_start + 1}"
    else:
        suggested_next = (
            f"search_text path={path} query={query}" if query else f"search_text path={path} query=<symbol-or-literal>"
        )
    message = (
        f"broad-read guard blocked read_file on {path}: the latest search_text for this target path returned zero matches, "
        "so a top-of-file read would discard the known search failure and widen context without a new anchor"
    )
    return {
        "reason": "broad_read_after_search_miss",
        "tool": tool,
        "path": path,
        "search_tool_call_id": latest_search.get("id"),
        "search_query": query,
        "message": message,
        "suggested_next": suggested_next,
        "guard_reason": (
            "reuse the last exact window or reformulate the search instead of restarting from the top of the file"
        ),
    }


def create_work_session(state, task, current_time=None, inherit_defaults=True):
    current_time = current_time or now_iso()
    existing = work_session_for_task(state, task.get("id"))
    if existing:
        existing["title"] = task.get("title") or existing.get("title") or ""
        task_goal = task.get("description") or task.get("title") or ""
        if task_goal:
            existing["goal"] = task_goal
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
        "active_work_todo": {},
        "startup_memory": startup_working_memory(task),
    }
    if inherit_defaults and latest and latest.get("default_options"):
        session["default_options"] = json.loads(json.dumps(latest.get("default_options") or {}))
    state.setdefault("work_sessions", []).append(session)
    return session, True


def startup_working_memory(task):
    task = task or {}
    task_id = task.get("id")
    title = str(task.get("title") or "work session").strip()
    goal = str(task.get("description") or title).strip()
    task_ref = f"task #{task_id}" if task_id is not None else "the selected task"
    return {
        "hypothesis": f"Start {task_ref}: {title}",
        "next_step": "continue the work session with one bounded model/tool step, then verify or record the next blocker",
        "plan_items": [],
        "open_questions": [],
        "source": "session_startup",
        "goal": goal,
    }


def safe_work_write_roots(roots):
    safe = []
    for root in roots or []:
        path = Path(root).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if is_sensitive_path(path):
            continue
        if root and root not in safe:
            safe.append(root)
    return safe


def _merge_option_list(current, incoming):
    merged = []
    for item in list(current or []) + list(incoming or []):
        if item and item not in merged:
            merged.append(item)
    return merged


def seed_work_session_runtime_defaults(
    session,
    *,
    allowed_read_roots=None,
    allowed_write_roots=None,
    allow_write=False,
    allow_verify=False,
    verify_command="",
    auth="",
    model_backend="",
    model="",
    base_url="",
    model_timeout=None,
    verify_timeout=None,
    tool_timeout=None,
    source="runtime",
    reason="",
    current_time=None,
):
    if not session:
        return {}
    defaults = session.setdefault("default_options", {})
    read_roots = [root for root in allowed_read_roots or [] if root]
    write_roots = safe_work_write_roots(allowed_write_roots or []) if allow_write else []
    if read_roots:
        defaults["allow_read"] = _merge_option_list(defaults.get("allow_read"), read_roots)
    if write_roots:
        defaults["allow_write"] = _merge_option_list(defaults.get("allow_write"), write_roots)
    if allow_verify and verify_command:
        defaults["allow_verify"] = True
        defaults["verify_command"] = verify_command
        defaults["verify_disabled"] = False
    for key, value in (
        ("auth", auth),
        ("model_backend", model_backend),
        ("model", model),
        ("base_url", base_url),
    ):
        if value:
            defaults[key] = value
    for key, value in (
        ("model_timeout", model_timeout),
        ("verify_timeout", verify_timeout),
        ("tool_timeout", tool_timeout),
    ):
        if value not in (None, ""):
            defaults[key] = float(value)
    if source or reason:
        note_text = f"{source or 'runtime'} started native work"
        if reason:
            note_text = f"{note_text}: {reason}"
        add_work_session_note(session, note_text, source="runtime", current_time=current_time)
    session["updated_at"] = current_time or now_iso()
    return defaults


def mark_work_session_runtime_owned(session, *, event_id=None, current_time=None):
    if not session:
        return session
    session["owner"] = "runtime"
    session["runtime_managed"] = True
    session.setdefault("runtime_started_at", current_time or now_iso())
    if event_id is not None:
        session["runtime_started_event_id"] = event_id
    session["updated_at"] = current_time or now_iso()
    return session


def work_session_started_by_runtime(session):
    if not session:
        return False
    return (
        session.get("runtime_managed") is True
        or session.get("owner") == "runtime"
        or bool(session.get("runtime_started_at"))
    )


def work_session_has_pending_write_approval(session):
    if not session:
        return False
    for call in session.get("tool_calls") or []:
        result = call.get("result") or {}
        if (
            call.get("tool") in WRITE_WORK_TOOLS
            and result.get("dry_run")
            and result.get("changed")
            and call.get("approval_status") not in NON_PENDING_APPROVAL_STATUSES
        ):
            return True
    return False


def work_session_runtime_command(session, task_id, *, follow=False, max_steps=1):
    defaults = (session or {}).get("default_options") or {}
    parts = ["work"]
    if task_id is not None:
        parts.append(task_id)
    parts.append("--follow" if follow else "--live")
    for key, flag in (
        ("auth", "--auth"),
        ("model_backend", "--model-backend"),
        ("model", "--model"),
        ("base_url", "--base-url"),
    ):
        if defaults.get(key):
            parts.extend([flag, defaults[key]])
    for root in defaults.get("allow_read") or []:
        parts.extend(["--allow-read", root])
    for root in defaults.get("allow_write") or []:
        parts.extend(["--allow-write", root])
    if defaults.get("allow_shell"):
        parts.append("--allow-shell")
    if defaults.get("allow_verify"):
        parts.append("--allow-verify")
    if defaults.get("verify_command"):
        parts.extend(["--verify-command", defaults["verify_command"]])
    if defaults.get("approval_mode"):
        parts.extend(["--approval-mode", defaults["approval_mode"]])
    if defaults.get("model_timeout") is not None:
        parts.extend(["--model-timeout", defaults["model_timeout"]])
    if defaults.get("verify_timeout") is not None:
        parts.extend(["--verify-timeout", defaults["verify_timeout"]])
    if defaults.get("tool_timeout") is not None:
        parts.extend(["--timeout", defaults["tool_timeout"]])
    if defaults.get("act_mode"):
        parts.extend(["--act-mode", defaults["act_mode"]])
    if defaults.get("compact_live"):
        parts.append("--compact-live")
    if defaults.get("quiet"):
        parts.append("--quiet")
    if defaults.get("no_prompt_approval"):
        parts.append("--no-prompt-approval")
    elif defaults.get("prompt_approval"):
        parts.append("--prompt-approval")
    parts.extend(["--max-steps", str(max_steps)])
    return mew_command(*parts)


def close_work_session(session, current_time=None):
    current_time = current_time or now_iso()
    session["status"] = "closed"
    session["updated_at"] = current_time
    return session


def request_work_session_stop(session, reason="", current_time=None, action="", submit_text=""):
    current_time = current_time or now_iso()
    session["stop_requested_at"] = current_time
    session["stop_reason"] = reason or "stop requested"
    if action:
        session["stop_action"] = action
    else:
        session.pop("stop_action", None)
    if submit_text:
        session["stop_submit_text"] = submit_text
    else:
        session.pop("stop_submit_text", None)
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
        "action": session.get("stop_action") or "",
        "submit_text": session.get("stop_submit_text") or "",
    }
    session["last_stop_request"] = stop
    session["stop_acknowledged_at"] = current_time
    session.pop("stop_requested_at", None)
    session.pop("stop_reason", None)
    session.pop("stop_action", None)
    session.pop("stop_submit_text", None)
    session["updated_at"] = current_time
    return stop


def mark_running_work_interrupted(state, current_time=None):
    current_time = current_time or now_iso()
    repairs = []
    for session in state.get("work_sessions", []):
        if not isinstance(session, dict):
            continue
        repairs.extend(mark_work_session_running_interrupted(session, current_time=current_time))
    return repairs


def mark_work_session_running_interrupted(session, current_time=None):
    current_time = current_time or now_iso()
    repairs = []
    if not isinstance(session, dict):
        return repairs
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


def mark_work_tool_call_interrupted(session, tool_call_id, current_time=None):
    current_time = current_time or now_iso()
    if not isinstance(session, dict):
        return []
    call = find_work_tool_call(session, tool_call_id)
    if not isinstance(call, dict) or call.get("status") != "running":
        return []
    recovery_hint = (
        f"Review work session #{session.get('id')} resume, verify world state, then retry or choose a new action."
    )
    call["status"] = "interrupted"
    call["finished_at"] = current_time
    call["error"] = call.get("error") or "Interrupted before the work tool completed."
    call["summary"] = call.get("summary") or "interrupted work tool call"
    call["recovery_hint"] = recovery_hint
    session["updated_at"] = current_time
    return [
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
    ]


def start_work_tool_call(state, session, tool, parameters):
    current_time = now_iso()
    write_intent = None
    write_intent_error = ""
    if tool in WRITE_WORK_TOOLS and (parameters or {}).get("apply"):
        try:
            write_intent = build_write_intent(tool, parameters or {})
        except (OSError, ValueError) as exc:
            write_intent_error = str(exc)
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
    if write_intent:
        tool_call["write_intent"] = write_intent
    if write_intent_error:
        tool_call["write_intent_error"] = write_intent_error
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


def find_model_turn_for_tool_call(session, tool_call_id):
    if not session or tool_call_id is None:
        return None
    target = str(tool_call_id)
    for turn in reversed(session.get("model_turns") or []):
        if any(str(value) == target for value in _turn_tool_call_ids(turn)):
            return turn
    return None


def work_turn_guidance_snapshot(turn):
    return clip_inline_text((turn or {}).get("guidance_snapshot") or (turn or {}).get("guidance") or "", 1000)


def start_work_model_turn(state, session, decision_plan, action_plan, action, guidance=""):
    current_time = now_iso()
    turn = {
        "id": next_id(state, "work_model_turn"),
        "session_id": session.get("id"),
        "task_id": session.get("task_id"),
        "status": "running",
        "decision_plan": dict(decision_plan or {}),
        "action_plan": dict(action_plan or {}),
        "action": dict(action or {}),
        "guidance_snapshot": clip_output(str(guidance or ""), 1000),
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


def update_work_model_turn_plan(state, session_id, turn_id, decision_plan, action_plan, action, model_metrics=None):
    session = find_work_session(state, session_id)
    turn = find_work_model_turn(session, turn_id)
    if not turn:
        return None
    current_time = now_iso()
    turn["decision_plan"] = dict(decision_plan or {})
    turn["action_plan"] = dict(action_plan or {})
    turn["action"] = dict(action or {})
    turn["summary"] = (action_plan or {}).get("summary") or (decision_plan or {}).get("summary") or turn.get("summary") or ""
    if model_metrics is not None:
        turn["model_metrics"] = dict(model_metrics or {})
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


def first_unquoted_shell_operator(command):
    text = command or ""
    in_single = False
    in_double = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and not in_single:
            escaped = True
            index += 1
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            index += 1
            continue
        if in_single or in_double:
            index += 1
            continue

        if char in {"\n", "\r"}:
            return char, "chain"
        two_chars = text[index : index + 2]
        if two_chars == "&>":
            end = index + 2
            if end < len(text) and text[end] == ">":
                end += 1
            return text[index:end], "redirection"
        if two_chars in SHELL_CHAIN_OPERATORS:
            return two_chars, "chain"
        if char in SHELL_CHAIN_OPERATORS:
            return char, "chain"
        if char in {">", "<"}:
            end = index + 1
            if end < len(text) and text[end] == char:
                end += 1
            if end < len(text) and text[end] == "&":
                end += 1
                while end < len(text) and text[end].isdigit():
                    end += 1
            return text[index:end], "redirection"
        if char.isdigit() and index + 1 < len(text) and text[index + 1] in {">", "<"}:
            end = index + 2
            if end < len(text) and text[end] == text[index + 1]:
                end += 1
            if end < len(text) and text[end] == "&":
                end += 1
                while end < len(text) and text[end].isdigit():
                    end += 1
            return text[index:end], "redirection"
        index += 1
    return None, ""


def reject_shell_control_tokens(command, *, tool_name="run_tests"):
    operator, kind = first_unquoted_shell_operator(command)
    if not operator:
        return
    if kind == "redirection":
        raise ValueError(
            f"{tool_name} executes one argv command without a shell; "
            f"redirection operator {operator!r} is not supported"
        )
    raise ValueError(
        f"{tool_name} executes one argv command without a shell; "
        f"split shell operator {operator!r} into separate commands"
    )


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
            line_start=parameters.get("line_start"),
            line_count=parameters.get("line_count"),
        )
    if tool == "search_text":
        return search_text(
            parameters.get("query") or "",
            parameters.get("path") or ".",
            allowed_read_roots,
            max_matches=parameters.get("max_matches", 50),
            context_lines=parameters.get("context_lines", 3),
            pattern=parameters.get("pattern"),
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
        reject_shell_control_tokens(command, tool_name="run_tests")
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
    defer_verify = bool(parameters.get("defer_verify"))
    if apply and not defer_verify and (not parameters.get("allow_verify") or not parameters.get("verify_command")):
        raise ValueError("applied writes require --allow-verify and --verify-command")
    if apply and not defer_verify:
        reject_shell_control_tokens(parameters.get("verify_command") or "", tool_name="write verification")
    if tool == "write_file" and "content" not in parameters:
        raise ValueError("write_file requires --content")
    if tool == "edit_file" and "old" not in parameters:
        raise ValueError("edit_file requires --old")
    if tool == "edit_file" and "new" not in parameters:
        raise ValueError("edit_file requires --new")
    if tool == "edit_file_hunks" and "edits" not in parameters:
        raise ValueError("edit_file_hunks requires --edits")

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
    elif tool == "edit_file_hunks":
        result = edit_file_hunks(
            path,
            parameters.get("edits") or [],
            allowed_write_roots,
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
    if apply and result.get("written") and defer_verify:
        result["verification_deferred"] = True
        result["rolled_back"] = False
    elif apply and result.get("written"):
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
        if result.get("exit_code") is None:
            return f"verification failed: {command_failure_reason(result)}"
        return f"verification failed with exit_code={result.get('exit_code')}"
    if tool in GIT_WORK_TOOLS and "exit_code" in result and result.get("exit_code") != 0:
        if result.get("exit_code") is None:
            return f"{tool} failed: {command_failure_reason(result)}"
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
            if exit_code is None:
                return f"verification failed: {command_failure_reason(result.get('verification') or {})}{suffix}"
            return f"verification failed with exit_code={exit_code}{suffix}"
    return ""


def clip_tail(text, max_chars=1200):
    text = text or ""
    if len(text) <= max_chars:
        return text
    tail = text[-max_chars:]
    line_break = tail.find("\n")
    if line_break >= 0:
        tail = tail[line_break + 1 :]
    return "[...snip...]\n" + tail


def append_work_tool_running_output(
    state,
    session_id,
    tool_call_id,
    stream_name,
    text,
    max_chars=DEFAULT_RUNNING_OUTPUT_MAX_CHARS,
):
    if stream_name not in ("stdout", "stderr") or not text:
        return None
    session = find_work_session(state, session_id)
    tool_call = find_work_tool_call(session, tool_call_id)
    if not tool_call or tool_call.get("status") != "running":
        return None
    running_output = tool_call.setdefault("running_output", {})
    current = running_output.get(stream_name) or ""
    combined = f"{current}{text}"
    clipped = clip_tail(combined, max_chars)
    truncated = bool(running_output.get(f"{stream_name}_truncated")) or len(combined) > max_chars
    current_time = now_iso()
    running_output[stream_name] = clipped
    running_output[f"{stream_name}_truncated"] = truncated or clipped.startswith("[...snip...]")
    running_output["updated_at"] = current_time
    running_output["max_chars"] = max_chars
    return running_output


def format_command_failure_summary(record, max_chars=1200):
    record = record or {}
    exit_code = record.get("exit_code")
    lines = [
        f"command: {record.get('command')}",
        f"cwd: {record.get('cwd')}",
        f"exit_code: {exit_code if exit_code is not None else 'unavailable'}",
    ]
    if exit_code is None:
        lines.append(f"failure: {command_failure_reason(record)}")
    stderr = record.get("stderr") or ""
    stdout = record.get("stdout") or ""
    if stderr:
        lines.extend(["stderr:", clip_tail(stderr, max_chars)])
    if stdout:
        lines.extend(["stdout:", clip_tail(stdout, max_chars)])
    return "\n".join(lines)


def command_failure_reason(record):
    record = record or {}
    if record.get("timed_out"):
        return "command timed out"
    argv = record.get("argv") or []
    if record.get("error_type") == "executable_not_found" and argv:
        return f"executable not found: {argv[0]}"
    stderr = (record.get("stderr") or "").strip()
    if stderr:
        return stderr.splitlines()[0]
    return "command did not exit"


def format_exit_code(value):
    return value if value is not None else "unavailable"


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


def _work_tool_exit_code(call):
    result = call.get("result") or {}
    verification = result.get("verification") or {}
    if "exit_code" in verification:
        return verification.get("exit_code")
    if "exit_code" in result:
        return result.get("exit_code")
    return None


def format_work_tool_observation_state(call):
    if not call:
        return ""
    tool = call.get("tool") or "unknown"
    status = call.get("status") or "unknown"
    text = f"latest tool #{call.get('id')} {status} {tool}"
    exit_code = _work_tool_exit_code(call)
    if exit_code is not None:
        text += f" exit={exit_code}"
    summary = compact_work_tool_summary(call)
    if summary:
        text += f": {' '.join(str(summary).split())}"
    return clip_output(text, 600)


def compact_work_tool_summary(call):
    tool = call.get("tool")
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    summary = call.get("summary") or call.get("error") or ""
    if call.get("status") in ("failed", "interrupted") and summary:
        if summary.startswith(f"{tool} {call.get('status')}:") or summary.startswith(f"{tool} failed:"):
            return clip_output(summary, 240)
        return f"{tool} {call.get('status')}: {clip_output(summary, 240)}"
    if tool == "read_file":
        suffix = " (truncated)" if result.get("truncated") else ""
        if result.get("line_start") is not None:
            line_end = result.get("line_end")
            line_span = f"{result.get('line_start')}-{line_end}" if line_end is not None else f"{result.get('line_start')}-EOF"
            next_text = f" next_line={result.get('next_line')}" if result.get("next_line") is not None else ""
            message = f" {result.get('message')}" if result.get("message") else ""
            return (
                f"Read file {result.get('path') or (call.get('parameters') or {}).get('path')} "
                f"size={result.get('size')} chars lines={line_span}{next_text}{suffix}{message}"
            )
        offset = result.get("offset") or 0
        next_text = f" next_offset={result.get('next_offset')}" if result.get("next_offset") is not None else ""
        return (
            f"Read file {result.get('path') or (call.get('parameters') or {}).get('path')} "
            f"size={result.get('size')} chars offset={offset}{next_text}{suffix}"
        )
    if tool == "search_text":
        suffix = " (truncated)" if result.get("truncated") else ""
        query = result.get("query") if result.get("query") is not None else parameters.get("query")
        pattern_value = result.get("pattern") if result.get("pattern") is not None else parameters.get("pattern")
        pattern = f" pattern={pattern_value!r}" if pattern_value else ""
        return (
            f"Searched {result.get('path') or parameters.get('path')} "
            f"for {query!r}{pattern} matches={len(result.get('matches') or [])}{suffix}"
        )
    if tool == "glob":
        suffix = " (truncated)" if result.get("truncated") else ""
        pattern = result.get("pattern") if result.get("pattern") is not None else parameters.get("pattern")
        return (
            f"Globbed {result.get('path') or parameters.get('path')} "
            f"for {pattern!r} matches={len(result.get('matches') or [])}{suffix}"
        )
    return summary


def work_tool_failure_record(call):
    result = call.get("result") or {}
    if call.get("tool") == "run_tests" and "exit_code" in result and result.get("exit_code") != 0:
        return result
    if call.get("tool") == "run_command" and "exit_code" in result and result.get("exit_code") != 0:
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


def work_recovery_read_root(call):
    path = work_call_path(call)
    if path:
        return path
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    return result.get("cwd") or parameters.get("cwd") or "."


def parent_path_for_observation(path):
    path = str(path or "").strip()
    if not path:
        return ""
    trimmed = path.rstrip("/\\")
    if not trimmed:
        return "/"
    separator_index = max(trimmed.rfind("/"), trimmed.rfind("\\"))
    if separator_index >= 0:
        parent = trimmed[:separator_index]
        if parent:
            return parent
        return "/" if trimmed.startswith("/") else "."
    return "."


def latest_prior_read_window_for_path(calls, path, before_id=None):
    normalized_path = _normalized_work_path_text(path)
    if not normalized_path:
        return {}

    def same_work_path(left, right):
        left_text = _normalized_work_path_text(left)
        right_text = _normalized_work_path_text(right)
        if not left_text or not right_text:
            return False
        if left_text == right_text:
            return True
        left_path = Path(left_text)
        right_path = Path(right_text)
        if not left_path.is_absolute() or not right_path.is_absolute():
            return False
        return left_path.resolve(strict=False) == right_path.resolve(strict=False)

    def candidate_paths(candidate):
        parameters = candidate.get("parameters") or {}
        result = candidate.get("result") or {}
        paths = [work_call_path(candidate), parameters.get("path"), result.get("path")]
        seen = set()
        unique = []
        for item in paths:
            text = _normalized_work_path_text(item)
            if text and text not in seen:
                seen.add(text)
                unique.append(text)
        return unique

    def call_matches_target(candidate):
        return any(same_work_path(candidate_path, normalized_path) for candidate_path in candidate_paths(candidate))

    for candidate in reversed(list(calls or [])):
        candidate_id = candidate.get("id")
        if before_id is not None and candidate_id is not None and candidate_id >= before_id:
            continue
        if candidate.get("tool") in WRITE_WORK_TOOLS and (candidate.get("result") or {}).get("written"):
            if call_matches_target(candidate):
                return {}
        if candidate.get("tool") != "read_file" or candidate.get("status") != "completed":
            continue
        if not call_matches_target(candidate):
            continue
        parameters = candidate.get("parameters") or {}
        result = candidate.get("result") or {}
        line_start = parameters.get("line_start") or result.get("line_start")
        line_count = parameters.get("line_count") or result.get("line_count")
        if line_start is None or line_count is None:
            continue
        return {"line_start": line_start, "line_count": line_count}
    return {}


def suggested_safe_reobserve_for_call(call, calls=None):
    if not isinstance(call, dict):
        return {}
    if call.get("recovery_status"):
        return {}
    failure_record = work_tool_failure_record(call)
    if call.get("status") not in ("failed", "interrupted") and not failure_record:
        return {}

    tool = call.get("tool")
    parameters = call.get("parameters") or {}
    call_result = call.get("result") or {}
    path = work_call_path(call)

    def suggestion(action, suggested_parameters, reason, kind="tool_observation"):
        result = {
            "source_tool_call_id": call.get("id"),
            "source_tool": tool,
            "kind": kind,
            "parameters": {key: value for key, value in suggested_parameters.items() if value not in (None, "")},
            "reason": reason,
        }
        if action:
            result["action"] = action
        return result

    if tool in WRITE_WORK_TOOLS and path:
        window = {
            key: parameters.get(key)
            for key in ("line_start", "line_count")
            if parameters.get(key) is not None
        }
        if not window:
            window = latest_prior_read_window_for_path(calls, path, before_id=call.get("id"))
        reason = "write/edit failed; safely re-read the target before planning another edit"
        if window:
            reason = "write/edit failed; safely re-read the latest target window before planning another edit"
        return suggestion(
            "read_file",
            {"path": path, **window},
            reason,
        )
    if tool == "read_file" and path:
        if call.get("status") == "interrupted":
            return suggestion(
                "read_file",
                {
                    "path": path,
                    "line_start": parameters.get("line_start"),
                    "line_count": parameters.get("line_count"),
                    "offset": parameters.get("offset"),
                },
                "read was interrupted; retry the bounded read after checking current read gates",
            )
        return suggestion(
            "inspect_dir",
            {"path": parent_path_for_observation(path)},
            "read failed; inspect the parent directory and read gates before retrying the file",
        )
    if tool in ("inspect_dir", "search_text", "glob"):
        suggested_parameters = {
            "path": path or parameters.get("path"),
            "query": parameters.get("query"),
            "pattern": parameters.get("pattern"),
            "max_matches": parameters.get("max_matches"),
        }
        return suggestion(tool, suggested_parameters, "inspection failed; retry the same safe observation if gates still allow it")
    if tool in GIT_WORK_TOOLS:
        return suggestion(
            tool,
            {
                "cwd": call_result.get("cwd") or parameters.get("cwd"),
                "base": call_result.get("base") or parameters.get("base"),
                "staged": call_result.get("staged") or parameters.get("staged"),
                "stat": call_result.get("stat") or parameters.get("stat"),
            },
            "git inspection failed; retry the read-only git observation before planning",
        )
    if tool in COMMAND_WORK_TOOLS:
        return suggestion(
            "",
            {
                "command": call_result.get("command") or parameters.get("command"),
                "cwd": call_result.get("cwd") or parameters.get("cwd"),
            },
            "command failed; review recorded stdout/stderr before rerunning side-effecting work",
            kind="recorded_output_review",
        )
    return {}


def repair_anchor_observation_for_path(
    path,
    calls=None,
    *,
    before_id=None,
    source_tool_call_id=None,
    source_tool="",
    reason="",
):
    normalized_path = _normalized_work_path_text(path)
    if not normalized_path:
        return {}
    window = latest_prior_read_window_for_path(calls, normalized_path, before_id=before_id)
    parameters = {"path": normalized_path}
    if window:
        parameters.update(window)
    observation = {
        "source_tool_call_id": source_tool_call_id,
        "source_tool": source_tool,
        "kind": "tool_observation",
        "action": "read_file",
        "parameters": parameters,
        "reason": reason
        or (
            "repair/reentry still points at this target path; reuse the latest window before broader search"
            if window
            else "repair/reentry still points at this target path; re-read it before broader search"
        ),
    }
    return {key: value for key, value in observation.items() if value not in (None, "", [])}


def _repair_anchor_key(observation):
    if not isinstance(observation, dict):
        return ()
    parameters = observation.get("parameters") or {}
    return (
        observation.get("action") or observation.get("kind") or "",
        _normalized_work_path_text(parameters.get("path")),
        parameters.get("line_start"),
        parameters.get("line_count"),
    )


def _append_repair_anchor(observations, observation, *, limit=4):
    if not observation:
        return
    key = _repair_anchor_key(observation)
    if not key:
        return
    if any(_repair_anchor_key(existing) == key for existing in observations):
        return
    observations.append(observation)
    del observations[limit:]


def paired_repair_anchor_paths_for_call(session, call):
    if not isinstance(call, dict):
        return []
    path = _normalized_work_path_text(work_call_path(call))
    if not path:
        return []
    paths = [path]
    parameters = call.get("parameters") or {}
    if _is_mew_source_path(path):
        discovered_tests = discovered_test_candidates_for_call(session, call, limit=1)
        paired_test_path = (
            discovered_tests[0]["path"] if discovered_tests else inferred_test_path_for_mew_source(path)
        )
        paired_test_path = _normalized_work_path_text(paired_test_path)
        if paired_test_path and paired_test_path not in paths:
            paths.append(paired_test_path)
    elif _is_test_path(path):
        paired_source_path = _normalized_work_path_text(parameters.get("paired_test_source_path"))
        if paired_source_path and paired_source_path not in paths:
            paths.append(paired_source_path)
    return paths


def build_repair_anchor_observations(session, calls, failures, working_memory=None, limit=4):
    observations = []
    call_by_id = {call.get("id"): call for call in calls or [] if call.get("id") is not None}
    for failure in reversed(list(failures or [])):
        safe_reobserve = failure.get("suggested_safe_reobserve") or {}
        if safe_reobserve.get("action") == "read_file":
            _append_repair_anchor(observations, safe_reobserve, limit=limit)
        call = call_by_id.get(failure.get("tool_call_id"))
        if not call or call.get("tool") not in WRITE_WORK_TOOLS:
            continue
        paired_paths = paired_repair_anchor_paths_for_call(session, call)
        for paired_path in paired_paths[1:]:
            if _is_test_path(paired_path):
                reason = (
                    "failed mew source edit likely still needs its paired tests surface; "
                    "reuse the latest paired test window before broader search"
                )
            else:
                reason = (
                    "failed paired test edit likely still needs its source surface; "
                    "reuse the latest paired source window before broader search"
                )
            observation = repair_anchor_observation_for_path(
                paired_path,
                calls=calls,
                before_id=call.get("id"),
                source_tool_call_id=call.get("id"),
                source_tool=call.get("tool") or "",
                reason=reason,
            )
            _append_repair_anchor(observations, observation, limit=limit)
    target_paths = _coerce_working_memory_target_paths((working_memory or {}).get("target_paths") or [])
    for target_path in target_paths:
        observation = repair_anchor_observation_for_path(
            target_path,
            calls=calls,
            source_tool_call_id=None,
            source_tool="working_memory",
        )
        _append_repair_anchor(observations, observation, limit=limit)
    return observations[:limit]


def _work_call_repeat_target(call):
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    if call.get("tool") in COMMAND_WORK_TOOLS:
        return result.get("command") or parameters.get("command") or ""
    if call.get("tool") in GIT_WORK_TOOLS:
        return result.get("command") or parameters.get("cwd") or result.get("cwd") or ""
    return work_call_path(call)


def _work_call_error_signature(call):
    result = call.get("result") or {}
    failure_record = work_tool_failure_record(call) or {}
    text = (
        call.get("error")
        or failure_record.get("stderr")
        or result.get("stderr")
        or call.get("summary")
        or ""
    )
    return clip_inline_text(text, 180)


def build_recurring_work_failures(calls, limit=3):
    groups = {}
    for call in calls or []:
        if not isinstance(call, dict):
            continue
        failure_record = work_tool_failure_record(call)
        if call.get("status") not in ("failed", "interrupted") and not failure_record:
            continue
        tool = call.get("tool") or "unknown"
        target = _work_call_repeat_target(call)
        signature = _work_call_error_signature(call)
        if not signature:
            continue
        key = (tool, target, signature)
        item = groups.setdefault(
            key,
            {
                "tool": tool,
                "target": target,
                "error": signature,
                "count": 0,
                "tool_call_ids": [],
                "last_tool_call_id": None,
            },
        )
        item["count"] += 1
        item["tool_call_ids"].append(call.get("id"))
        item["last_tool_call_id"] = call.get("id")
    repeated = [item for item in groups.values() if item.get("count", 0) >= 2]
    repeated.sort(key=lambda item: item.get("last_tool_call_id") or 0)
    return repeated[-limit:]


def build_low_yield_observation_warnings(calls, *, threshold=3, limit=3):
    groups = {}
    for call in calls or []:
        if not isinstance(call, dict) or call.get("tool") != "search_text" or call.get("status") != "completed":
            continue
        result = call.get("result") or {}
        matches = result.get("matches")
        if matches is None:
            continue
        path = result.get("path") or (call.get("parameters") or {}).get("path") or ""
        pattern = result.get("pattern") or (call.get("parameters") or {}).get("pattern") or ""
        key = (path, pattern)
        if matches:
            groups.pop(key, None)
            continue
        item = groups.setdefault(
            key,
            {
                "tool": "search_text",
                "path": path,
                "pattern": pattern,
                "count": 0,
                "queries": [],
                "tool_call_ids": [],
                "last_tool_call_id": None,
                "reason": "repeated search_text calls on this path returned zero matches",
                "suggested_next": "stop searching this same surface; use a targeted read, broaden the path once, edit from known context, or finish with a concrete replan",
            },
        )
        item["count"] += 1
        query = result.get("query") or (call.get("parameters") or {}).get("query") or ""
        if query and query not in item["queries"]:
            item["queries"].append(query)
        item["tool_call_ids"].append(call.get("id"))
        item["last_tool_call_id"] = call.get("id")
    warnings = [item for item in groups.values() if item.get("count", 0) >= threshold]
    warnings.sort(key=lambda item: item.get("last_tool_call_id") or 0)
    for item in warnings:
        item["queries"] = item["queries"][-5:]
        item["tool_call_ids"] = item["tool_call_ids"][-10:]
    return warnings[-limit:]


def _search_result_first_match_line(result):
    matches = (result or {}).get("matches") or []
    if not matches:
        return None
    first = matches[0]
    if isinstance(first, dict):
        for key in ("line", "line_start"):
            value = first.get(key)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
    if isinstance(first, str):
        parts = first.split(":", 2)
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except (TypeError, ValueError):
                pass
    return None


def build_redundant_search_observations(calls, *, limit=3, read_line_count=20):
    prior_success = {}
    repeated = []
    for call in calls or []:
        if not isinstance(call, dict) or call.get("tool") != "search_text" or call.get("status") != "completed":
            continue
        result = call.get("result") or {}
        matches = result.get("matches")
        if not matches:
            continue
        path = result.get("path") or (call.get("parameters") or {}).get("path") or ""
        query = result.get("query") or (call.get("parameters") or {}).get("query") or ""
        pattern = result.get("pattern") or (call.get("parameters") or {}).get("pattern") or ""
        first_match_line = _search_result_first_match_line(result)
        key = (path, query, pattern)
        prior = prior_success.get(key)
        if prior:
            repeated.append(
                {
                    "tool": "search_text",
                    "path": path,
                    "query": query,
                    "pattern": pattern,
                    "count": prior.get("count", 1) + 1,
                    "prior_tool_call_id": prior.get("tool_call_id"),
                    "last_tool_call_id": call.get("id"),
                    "prior_first_match_line": prior.get("first_match_line"),
                    "latest_first_match_line": first_match_line,
                    "reason": "same successful search_text was repeated instead of converting the anchored result into a narrow read_file",
                    "suggested_next": (
                        f"read_file path={path} line_start={prior.get('first_match_line') or first_match_line} "
                        f"line_count={read_line_count}"
                    ).strip(),
                }
            )
        prior_success[key] = {
            "tool_call_id": call.get("id"),
            "first_match_line": first_match_line,
            "count": (prior or {}).get("count", 0) + 1,
        }
    repeated.sort(key=lambda item: item.get("last_tool_call_id") or 0)
    return repeated[-limit:]


def _read_file_call_line_window(call):
    if not isinstance(call, dict) or call.get("tool") != "read_file":
        return None
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    start = result.get("line_start")
    end = result.get("line_end")
    if start is None:
        start = parameters.get("line_start")
    if end is None and start is not None:
        line_count = result.get("line_count")
        if line_count is None:
            line_count = parameters.get("line_count")
        try:
            if line_count is not None:
                end = int(start) + int(line_count) - 1
        except (TypeError, ValueError):
            end = None
    try:
        if start is not None and end is not None:
            return (int(start), int(end))
    except (TypeError, ValueError):
        return None
    return None


def build_adjacent_read_observations(calls, *, limit=3, gap_lines=2):
    observations = []
    cluster = None
    for call in calls or []:
        if not isinstance(call, dict) or call.get("tool") != "read_file" or call.get("status") != "completed":
            continue
        result = call.get("result") or {}
        path = result.get("path") or (call.get("parameters") or {}).get("path") or ""
        line_window = _read_file_call_line_window(call)
        if not path or line_window is None:
            cluster = None
            continue
        start, end = line_window
        if cluster and cluster.get("path") == path and start <= cluster["merged_end"] + gap_lines + 1:
            cluster["count"] += 1
            cluster["last_tool_call_id"] = call.get("id")
            cluster["merged_start"] = min(cluster["merged_start"], start)
            cluster["merged_end"] = max(cluster["merged_end"], end)
            cluster["context_truncated"] = cluster["context_truncated"] or bool(result.get("context_truncated"))
            continue
        if cluster and cluster.get("count", 0) >= 2:
            observations.append(
                {
                    "tool": "read_file",
                    "path": cluster["path"],
                    "count": cluster["count"],
                    "first_tool_call_id": cluster["first_tool_call_id"],
                    "last_tool_call_id": cluster["last_tool_call_id"],
                    "merged_line_start": cluster["merged_start"],
                    "merged_line_end": cluster["merged_end"],
                    "context_truncated": cluster["context_truncated"],
                    "reason": "adjacent or overlapping read_file windows on the same path suggest one merged read would be cheaper than inching through small spans",
                    "suggested_next": (
                        f"read_file path={cluster['path']} line_start={cluster['merged_start']} "
                        f"line_count={cluster['merged_end'] - cluster['merged_start'] + 1}"
                    ),
                }
            )
        cluster = {
            "path": path,
            "count": 1,
            "first_tool_call_id": call.get("id"),
            "last_tool_call_id": call.get("id"),
            "merged_start": start,
            "merged_end": end,
            "context_truncated": bool(result.get("context_truncated")),
        }
    if cluster and cluster.get("count", 0) >= 2:
        observations.append(
            {
                "tool": "read_file",
                "path": cluster["path"],
                "count": cluster["count"],
                "first_tool_call_id": cluster["first_tool_call_id"],
                "last_tool_call_id": cluster["last_tool_call_id"],
                "merged_line_start": cluster["merged_start"],
                "merged_line_end": cluster["merged_end"],
                "context_truncated": cluster["context_truncated"],
                "reason": "adjacent or overlapping read_file windows on the same path suggest one merged read would be cheaper than inching through small spans",
                "suggested_next": (
                    f"read_file path={cluster['path']} line_start={cluster['merged_start']} "
                    f"line_count={cluster['merged_end'] - cluster['merged_start'] + 1}"
                ),
            }
        )
    observations.sort(key=lambda item: item.get("last_tool_call_id") or 0)
    return observations[-limit:]


def latest_work_verify_command(calls, task=None):
    command = (task or {}).get("command") or ""
    for call in calls:
        result = call.get("result") or {}
        if result.get("narrow_verify_command"):
            continue
        if call.get("tool") == "run_tests" and result.get("command"):
            command = result.get("command")
        verification = result.get("verification") or {}
        if verification.get("narrow_verify_command"):
            continue
        if verification.get("command"):
            command = verification.get("command")
    return command


def _same_surface_audit_note_state(note_text):
    text = str(note_text or "").casefold()
    if not any(
        marker in text
        for marker in (
            "same-surface audit",
            "same surface audit",
            "sibling code path",
            "sibling surface",
            "同系コード",
            "周辺コード",
        )
    ):
        return None
    if any(
        marker in text
        for marker in (
            "not checked",
            "not covered",
            "not done",
            "not inspected",
            "still needed",
            "needs audit",
            "audit needed",
            "pending audit",
            "未確認",
            "未完了",
        )
    ):
        return False
    if any(
        marker in text
        for marker in (
            "checked",
            "covered",
            "out of scope",
            "out-of-scope",
            "done",
            "inspected",
            "reviewed",
            "確認",
            "対象外",
        )
    ):
        return True
    return None


def _same_surface_audit_item_time(item):
    return str(
        (item or {}).get("finished_at")
        or (item or {}).get("updated_at")
        or (item or {}).get("created_at")
        or (item or {}).get("started_at")
        or ""
    )


def _same_surface_audit_noted(session, latest_source_edit_at):
    latest_state = None
    for note in (session or {}).get("notes") or []:
        note_time = str((note or {}).get("created_at") or "")
        if latest_source_edit_at and (not note_time or note_time < latest_source_edit_at):
            continue
        state = _same_surface_audit_note_state((note or {}).get("text") or "")
        if state is not None:
            latest_state = state
    return bool(latest_state)


def _same_surface_audit_display_path(path):
    normalized = _normalized_work_path_text(path)
    if normalized == "src/mew" or normalized.startswith("src/mew/"):
        return normalized
    marker = "/src/mew/"
    if marker in normalized:
        return f"src/mew/{normalized.split(marker, 1)[1]}"
    return normalized


def build_same_surface_audit_checkpoint(session, task, calls):
    if (task or {}).get("kind") != "coding" or (task or {}).get("status") == "done":
        return {}
    paths = []
    latest_source_edit_at = ""
    for call in calls or []:
        if call.get("tool") not in WRITE_WORK_TOOLS:
            continue
        raw_path = work_call_path(call)
        if not raw_path or not _is_mew_source_path(raw_path):
            continue
        path = _same_surface_audit_display_path(raw_path)
        result = call.get("result") or {}
        if not (result.get("changed") or result.get("applied") or result.get("written")):
            continue
        if path not in paths:
            paths.append(path)
        edit_time = _same_surface_audit_item_time(call)
        if edit_time and edit_time >= latest_source_edit_at:
            latest_source_edit_at = edit_time
    if not paths:
        return {}
    noted = _same_surface_audit_noted(session, latest_source_edit_at)
    return {
        "status": "noted" if noted else "needed",
        "reason": "src/mew source edits should inspect sibling code paths on the same surface before done",
        "paths": paths[-3:],
        "prompt": "search nearby command/json/control peers and record why they are covered or out of scope",
    }


def latest_work_verification_state(calls, task=None):
    for call in reversed(list(calls or [])):
        result = call.get("result") or {}
        verification = result.get("verification") or {}
        if "exit_code" in verification:
            status = "passed" if verification.get("exit_code") == 0 else "failed"
            if _pytest_zero_tests_result(verification):
                status = "invalid"
            return {
                "kind": f"{call.get('tool')}_verification",
                "status": status,
                "command": verification.get("command") or "",
                "cwd": verification.get("cwd") or "",
                "exit_code": verification.get("exit_code"),
                "finished_at": verification.get("finished_at") or call.get("finished_at"),
                "tool_call_id": call.get("id"),
                "narrow_verify_command": bool(verification.get("narrow_verify_command")),
            }
        if call.get("tool") == "run_tests" and "exit_code" in result:
            status = "passed" if result.get("exit_code") == 0 else "failed"
            if _pytest_zero_tests_result(result):
                status = "invalid"
            return {
                "kind": "run_tests",
                "status": status,
                "command": result.get("command") or (call.get("parameters") or {}).get("command") or "",
                "cwd": result.get("cwd") or (call.get("parameters") or {}).get("cwd") or "",
                "exit_code": result.get("exit_code"),
                "finished_at": result.get("finished_at") or call.get("finished_at"),
                "tool_call_id": call.get("id"),
                "narrow_verify_command": bool(result.get("narrow_verify_command")),
            }
    command = latest_work_verify_command(calls, task=task)
    if command:
        return {
            "kind": "configured_verification",
            "status": "not_run",
            "command": command,
            "cwd": ".",
            "exit_code": None,
            "finished_at": "",
        }
    return {}


def format_work_verification_state(state):
    if not state:
        return ""
    command = state.get("command") or ""
    status = state.get("status") or "unknown"
    if status == "not_run":
        prefix = "verification configured but not run"
    else:
        prefix = f"last verification {status}"
    exit_text = "" if state.get("exit_code") is None else f" exit={state.get('exit_code')}"
    command_text = f": {command}" if command else ""
    return f"{prefix}{exit_text}{command_text}"


def _coerce_open_questions(value):
    if isinstance(value, list):
        return [clip_output(str(item), 300) for item in value if str(item).strip()][:5]
    if isinstance(value, str) and value.strip():
        return [clip_output(value, 300)]
    return []


def _coerce_working_memory_target_paths(value):
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []
    paths = []
    for item in candidates:
        path = _working_memory_target_path_text(item)
        if not path or path in paths:
            continue
        paths.append(path)
        if len(paths) >= 5:
            break
    return paths


def _relevant_resume_target_paths(target_paths):
    paths = [str(item or "").strip() for item in (target_paths or []) if str(item or "").strip()]
    if len(paths) <= 5:
        return paths
    relevant = list(paths[:5])
    if not any(path.startswith("tests/") for path in relevant):
        for path in paths[5:]:
            if path.startswith("tests/") and path not in relevant:
                relevant.append(path)
                break
    return relevant


def _coerce_working_memory_plan_items(value):
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []
    items = []
    for item in candidates:
        text = clip_output(str(item or "").strip(), 240)
        if not text or text in items:
            continue
        items.append(text)
        if len(items) >= 3:
            break
    return items


def _turn_action_target_paths(turn):
    if not turn:
        return []
    action = turn.get("action") or {}
    paths = []
    for candidate in [action] + list(action.get("tools") or []):
        path = _working_memory_target_path_text(candidate.get("path"))
        if not path or path in paths:
            continue
        paths.append(path)
        if len(paths) >= 5:
            break
    return paths


def _normalize_working_memory(raw, turn=None, verification_state=None, source="model"):
    if not isinstance(raw, dict):
        return {}
    observed_verified_state = ""
    if (verification_state or {}).get("status") != "not_run":
        observed_verified_state = format_work_verification_state(verification_state)
    memory = {
        "hypothesis": clip_output(str(raw.get("hypothesis") or raw.get("current_hypothesis") or "").strip(), 600),
        "next_step": clip_output(str(raw.get("next_step") or raw.get("next_intended_step") or "").strip(), 600),
        "plan_items": _coerce_working_memory_plan_items(raw.get("plan_items") or raw.get("checklist") or []),
        "open_questions": _coerce_open_questions(raw.get("open_questions") or raw.get("questions") or []),
        "last_verified_state": clip_output(
            observed_verified_state or str(raw.get("last_verified_state") or "").strip(),
            600,
        ),
        "target_paths": _coerce_working_memory_target_paths(raw.get("target_paths") or raw.get("paths") or []),
    }
    for path in _turn_action_target_paths(turn):
        if path not in memory["target_paths"]:
            memory["target_paths"].append(path)
        if len(memory["target_paths"]) >= 5:
            break
    if not memory["last_verified_state"]:
        memory["last_verified_state"] = clip_output(format_work_verification_state(verification_state), 600)
    if not any(
        memory.get(key)
        for key in ("hypothesis", "next_step", "plan_items", "open_questions", "last_verified_state", "target_paths")
    ):
        return {}
    if turn:
        memory["model_turn_id"] = turn.get("id")
        memory["status"] = turn.get("status")
        memory["updated_at"] = turn.get("finished_at") or turn.get("started_at") or ""
    memory["source"] = source
    return memory


def _turn_tool_call_ids(turn):
    if not turn:
        return []
    ids = []
    if turn.get("tool_call_id") is not None:
        ids.append(turn.get("tool_call_id"))
    for value in turn.get("tool_call_ids") or []:
        if value is not None:
            ids.append(value)
    return ids


def _normalized_work_path_text(path):
    return str(path or "").strip().replace("\\", "/")


def _working_memory_target_path_text(path):
    normalized = _normalized_work_path_text(path)
    if not normalized:
        return ""
    try:
        candidate = Path(normalized)
        if candidate.is_absolute():
            try:
                normalized = candidate.relative_to(Path.cwd()).as_posix()
            except ValueError:
                normalized = candidate.as_posix()
    except (OSError, RuntimeError, ValueError):
        return normalized
    return normalized


def _is_mew_source_path(path):
    normalized = _normalized_work_path_text(path)
    return normalized == "src/mew" or normalized.startswith("src/mew/") or "/src/mew/" in normalized


def inferred_test_path_for_mew_source(path):
    return convention_test_path_for_mew_source(path)


def _test_discovery_hint_for_call(session, call):
    values = []
    for key in ("title", "description", "goal", "objective", "focus"):
        value = (session or {}).get(key)
        if value:
            values.append(str(value))
    for note in ((session or {}).get("notes") or [])[-5:]:
        if note.get("text"):
            values.append(str(note.get("text")))
    for source in ((call or {}).get("parameters") or {}, (call or {}).get("result") or {}):
        for key in ("path", "content", "old", "new", "diff", "summary"):
            value = source.get(key)
            if value:
                values.append(str(value))
    return "\n".join(values)


def discovered_test_candidates_for_call(session, call, *, limit=5):
    source_path = work_call_path(call)
    if not source_path:
        return []
    return discover_tests_for_source(
        source_path,
        hint_text=_test_discovery_hint_for_call(session, call),
        limit=limit,
    )


def suggested_verify_command_for_call_path(source_path, *, hint_text=""):
    discovered = discover_tests_for_source(source_path, hint_text=hint_text, limit=1)
    test_path = discovered[0]["path"] if discovered else inferred_test_path_for_mew_source(source_path)
    if not test_path or not Path(test_path).is_file():
        return {}
    test_module = Path(test_path).with_suffix("").as_posix().replace("/", ".")
    return {
        "source_path": source_path,
        "test_path": test_path,
        "command": f"uv run python -m unittest {test_module}",
        "reason": (
            "mew source edit has an existing discovered test module"
            if discovered
            else "mew source edit has a matching test module"
        ),
    }


def suggested_verify_commands_for_calls(calls):
    suggestions = []
    seen_tests = set()
    for call in reversed(list(calls or [])):
        result = (call or {}).get("result") or {}
        if (
            (call or {}).get("tool") not in WRITE_WORK_TOOLS
            or (call or {}).get("status") != "completed"
            or not result.get("changed")
            or not result.get("written")
        ):
            continue
        source_path = work_call_path(call)
        suggestion = suggested_verify_command_for_call_path(
            source_path,
            hint_text=_test_discovery_hint_for_call(None, call),
        )
        if suggestion:
            test_path = suggestion.get("test_path") or ""
            if test_path in seen_tests:
                continue
            seen_tests.add(test_path)
            suggestions.append(suggestion)
    return suggestions


def suggested_verify_command_for_calls(calls):
    suggestions = suggested_verify_commands_for_calls(calls)
    if suggestions:
        return suggestions[0]
    return {}


def _verification_command_covers_suggestion(command, suggestion):
    command = str(command or "").strip()
    if not command or not suggestion:
        return False
    test_path = str(suggestion.get("test_path") or "").replace("\\", "/")
    test_module = Path(test_path).with_suffix("").as_posix().replace("/", ".") if test_path else ""
    try:
        tokens = [token.replace("\\", "/") for token in shlex.split(command)]
    except ValueError:
        tokens = command.replace("\\", "/").split()
    for token in tokens:
        normalized_token = token.removeprefix("./")
        if test_path and (
            normalized_token == test_path
            or normalized_token.startswith(f"{test_path}::")
        ):
            return True
        if test_module and (
            token == test_module
            or token.startswith(f"{test_module}.")
        ):
            return True
    if any(token in ("tests", "tests/") or token.endswith("/tests") for token in tokens):
        return True
    has_pytest = any(Path(token).name == "pytest" or token.endswith("/pytest") for token in tokens)
    has_unittest = "-m" in tokens and "unittest" in tokens
    if has_pytest or has_unittest:
        has_specific_test_target = any(
            token.removeprefix("./").startswith("tests/")
            or token.startswith("tests.")
            or "::" in token
            for token in tokens
        )
        return not has_specific_test_target
    if any(Path(token).name in ("tox", "nox") for token in tokens):
        return True
    if "poe" in tokens and any(token in ("test", "tests") for token in tokens):
        return True
    return False


def verification_command_covers_suggestion(command, suggestion):
    return _verification_command_covers_suggestion(command, suggestion)


def _source_edit_verify_suggestions_for_calls(calls, include_dry_run=False):
    suggestions = []
    seen_tests = set()
    for call in reversed(list(calls or [])):
        result = (call or {}).get("result") or {}
        pending_dry_run = (
            result.get("dry_run")
            and not result.get("written")
            and (call or {}).get("approval_status") not in NON_PENDING_APPROVAL_STATUSES
        )
        if (
            (call or {}).get("tool") not in WRITE_WORK_TOOLS
            or (call or {}).get("status") != "completed"
            or not result.get("changed")
            or not (result.get("written") or (include_dry_run and pending_dry_run))
        ):
            continue
        source_path = work_call_path(call)
        suggestion = suggested_verify_command_for_call_path(source_path)
        if not suggestion:
            continue
        test_path = suggestion.get("test_path") or ""
        if test_path in seen_tests:
            continue
        seen_tests.add(test_path)
        suggestion = dict(suggestion)
        suggestion["source_tool_call_id"] = call.get("id")
        suggestion["source_pending_approval"] = bool(pending_dry_run)
        suggestions.append(suggestion)
    return suggestions


def verification_coverage_warning_for_calls(calls, task=None):
    suggestions = suggested_verify_commands_for_calls(calls)
    if not suggestions:
        return {}
    verification_state = latest_work_verification_state(calls, task=task)
    command = verification_state.get("command") or latest_work_verify_command(calls, task=task)
    if not command or verification_state.get("status") != "passed":
        return {}
    uncovered = [suggestion for suggestion in suggestions if not _verification_command_covers_suggestion(command, suggestion)]
    if not uncovered:
        return {}
    suggestion = uncovered[0]
    return {
        "command": command,
        "status": verification_state.get("status") or "unknown",
        "source_path": suggestion.get("source_path") or "",
        "expected_test_path": suggestion.get("test_path") or "",
        "expected_command": suggestion.get("command") or "",
        "uncovered_count": len(uncovered),
        "uncovered_tests": [item.get("test_path") or "" for item in uncovered[:5]],
        "reason": "latest verification command does not appear to cover the matching test for this mew source edit",
    }


def _verification_command_uses_selector(command, suggestions=None):
    command = str(command or "").strip()
    if not command:
        return False
    try:
        tokens = [token.replace("\\", "/") for token in shlex.split(command)]
    except ValueError:
        tokens = command.replace("\\", "/").split()
    selector_flags = {"-k", "-m", "--deselect", "--lf", "--ff", "--failed-first", "--last-failed"}
    pytest_indices = [
        index
        for index, token in enumerate(tokens)
        if Path(token).name == "pytest" or token.endswith("/pytest")
    ]
    pytest_args = tokens[pytest_indices[-1] + 1 :] if pytest_indices else []
    for token in pytest_args:
        if token in selector_flags or token.startswith(("-k=", "-m=", "--deselect=", "--keyword=")):
            return True
    for token in tokens:
        if "::" in token:
            return True
    for suggestion in suggestions or []:
        test_path = str(suggestion.get("test_path") or "").replace("\\", "/")
        test_module = Path(test_path).with_suffix("").as_posix().replace("/", ".") if test_path else ""
        if not test_module:
            continue
        for token in tokens:
            normalized_token = token.removeprefix("./")
            if normalized_token.startswith(f"{test_path}::"):
                return True
            if token.startswith(f"{test_module}."):
                return True
    return False


def _pytest_zero_tests_result(record):
    command = str((record or {}).get("command") or "").strip()
    if not command or (record or {}).get("exit_code") != 5:
        return False
    try:
        tokens = [token.replace("\\", "/") for token in shlex.split(command)]
    except ValueError:
        tokens = command.replace("\\", "/").split()
    has_pytest = any(Path(token).name == "pytest" or token.endswith("/pytest") for token in tokens)
    has_pytest = has_pytest or any(
        token == "-m" and index + 1 < len(tokens) and tokens[index + 1] == "pytest"
        for index, token in enumerate(tokens)
    )
    if not has_pytest:
        return False
    output = "\n".join(str((record or {}).get(key) or "") for key in ("stdout", "stderr", "summary", "error"))
    normalized = output.lower()
    return "no tests ran" in normalized or "collected 0 items" in normalized or "not found:" in normalized


def verification_confidence_checkpoint_for_calls(calls, task=None):
    suggestions = _source_edit_verify_suggestions_for_calls(calls, include_dry_run=True)
    if not suggestions:
        return {}
    expected_commands = []
    source_paths = []
    pending_source_paths = []
    latest_source_tool_call_id = None
    for suggestion in suggestions:
        command = suggestion.get("command") or ""
        source_path = suggestion.get("source_path") or ""
        if command and command not in expected_commands:
            expected_commands.append(command)
        if source_path and source_path not in source_paths:
            source_paths.append(source_path)
        if suggestion.get("source_pending_approval") and source_path not in pending_source_paths:
            pending_source_paths.append(source_path)
        tool_call_id = suggestion.get("source_tool_call_id")
        if isinstance(tool_call_id, int):
            latest_source_tool_call_id = max(latest_source_tool_call_id or tool_call_id, tool_call_id)

    base = {
        "source_paths": source_paths[:5],
        "expected_commands": expected_commands[:5],
        "expected_command": expected_commands[0] if expected_commands else "",
        "latest_source_tool_call_id": latest_source_tool_call_id,
        "finish_ready": False,
        "approval_ready": False,
    }
    if pending_source_paths:
        return {
            **base,
            "status": "pending_approval",
            "confidence": "low",
            "pending_source_paths": pending_source_paths[:5],
            "reason": "mew source edits are still dry-run or awaiting approval; verify the applied change before finish",
        }

    verification_state = latest_work_verification_state(calls, task=task)
    command = verification_state.get("command") or latest_work_verify_command(calls, task=task)
    latest_verification_tool_call_id = verification_state.get("tool_call_id")
    latest_status = verification_state.get("status") or ("not_run" if command else "missing")
    checkpoint = {
        **base,
        "command": command,
        "latest_status": latest_status,
        "latest_verification_kind": verification_state.get("kind") or "",
        "latest_verification_tool_call_id": latest_verification_tool_call_id,
        "latest_verification_finished_at": verification_state.get("finished_at") or "",
    }

    if not command:
        return {
            **checkpoint,
            "status": "missing",
            "confidence": "low",
            "reason": "no verification command has run for the latest mew source edit",
        }
    if isinstance(latest_source_tool_call_id, int) and isinstance(latest_verification_tool_call_id, int):
        if latest_verification_tool_call_id < latest_source_tool_call_id:
            return {
                **checkpoint,
                "status": "stale",
                "confidence": "low",
                "reason": "latest passing verifier ran before the latest mew source edit",
            }
    if latest_status == "invalid":
        return {
            **checkpoint,
            "status": "invalid",
            "confidence": "low",
            "narrow_command": _verification_command_uses_selector(command, suggestions),
            "reason": "latest pytest verifier matched no tests; broaden the selector to the inferred test module or suite before finish",
        }
    if latest_status != "passed":
        return {
            **checkpoint,
            "status": "failed" if latest_status == "failed" else "missing",
            "confidence": "low",
            "reason": "latest verifier has not passed after the latest mew source edit",
        }

    uncovered = [suggestion for suggestion in suggestions if not _verification_command_covers_suggestion(command, suggestion)]
    if uncovered:
        return {
            **checkpoint,
            "status": "partial",
            "confidence": "medium",
            "uncovered_tests": [item.get("test_path") or "" for item in uncovered[:5]],
            "reason": "latest verifier passed, but does not appear to cover every inferred paired test",
        }

    narrow = _verification_command_uses_selector(command, suggestions)
    if narrow:
        return {
            **checkpoint,
            "status": "narrow",
            "confidence": "medium",
            "narrow_command": True,
            "reason": "latest verifier used a selector or node-id; run the full inferred test module or a broader suite before finish",
        }

    return {
        **checkpoint,
        "status": "verified",
        "confidence": "high",
        "finish_ready": True,
        "approval_ready": True,
        "reason": "latest passing verifier appears to cover the inferred paired tests for mew source edits",
    }


def _is_test_path(path):
    normalized = _normalized_work_path_text(path)
    return normalized == "tests" or normalized.startswith("tests/") or "/tests/" in normalized


def work_approval_default_defer_reason(call):
    parameters = (call or {}).get("parameters") or {}
    if not parameters.get("defer_verify_on_approval"):
        return ""
    path = work_call_path(call)
    if not _is_test_path(path):
        return ""
    source_path = str(parameters.get("paired_test_source_path") or "").strip()
    if source_path:
        return f"paired test for {source_path} should wait for its source edit before verification"
    return "paired test approval should wait for its source edit before verification"


def _work_call_changed_write(call):
    result = (call or {}).get("result") or {}
    return (call or {}).get("tool") in WRITE_WORK_TOOLS and bool(result.get("changed"))


def _work_call_counts_as_test_pair(call):
    return (
        (call or {}).get("status") == "completed"
        and _work_call_changed_write(call)
        and call.get("approval_status") not in ("rejected", "failed", APPROVAL_STATUS_INDETERMINATE)
    )


def work_write_pairing_status(session, call):
    """Return advisory test-pairing status for resident edits to mew source files."""
    if not session or not call or not _work_call_changed_write(call):
        return {}
    source_path = work_call_path(call)
    if not _is_mew_source_path(source_path):
        return {}

    paired = None
    for candidate in session.get("tool_calls") or []:
        if candidate.get("id") == call.get("id"):
            continue
        if _work_call_counts_as_test_pair(candidate) and _is_test_path(work_call_path(candidate)):
            paired = candidate
            break

    if paired:
        return {
            "status": "ok",
            "source_path": source_path,
            "required": "tests/** write/edit in the same work session",
            "paired_tool_call_id": paired.get("id"),
            "paired_path": work_call_path(paired),
        }
    discovered_tests = discovered_test_candidates_for_call(session, call)
    suggested_test_path = (
        discovered_tests[0]["path"] if discovered_tests else inferred_test_path_for_mew_source(source_path)
    )
    suggestion_reason = ""
    if discovered_tests:
        suggestion_reason = discovered_tests[0].get("reason") or "existing test file references this source"
    elif suggested_test_path:
        suggestion_reason = "no existing test reference found; convention fallback from the src/mew source filename"
    return {
        "status": "missing_test_edit",
        "source_path": source_path,
        "required": "tests/** write/edit in the same work session",
        "reason": "mew source edit has no paired test write/edit in the same work session",
        "advisory": True,
        "suggested_test_path": suggested_test_path,
        "suggestion_reason": suggestion_reason,
        "discovered_test_paths": [item["path"] for item in discovered_tests],
    }


def _latest_tool_call_after_memory(turn, calls):
    if not turn or not calls:
        return None
    turn_tool_call_ids = _turn_tool_call_ids(turn)
    if not turn_tool_call_ids:
        return None
    # A turn's working_memory is written before its selected tool executes, so
    # same-turn tool results can already make the recorded next_step stale.
    max_turn_tool_call_id = max(turn_tool_call_ids)
    for call in reversed(calls):
        call_id = call.get("id")
        if call_id in turn_tool_call_ids:
            return call
        if call_id is not None and call_id > max_turn_tool_call_id:
            return call
    return None


def _annotate_working_memory_with_latest_tool(memory, turn, calls):
    if not memory:
        return memory
    stale_call = _latest_tool_call_after_memory(turn, calls)
    if stale_call:
        path = _working_memory_target_path_text(work_call_path(stale_call))
        target_paths = memory.setdefault("target_paths", [])
        if path:
            if path not in target_paths:
                target_paths.append(path)
            if _is_mew_source_path(path):
                discovered = discover_tests_for_source(path, limit=1)
                paired_test_path = (
                    _working_memory_target_path_text((discovered[0] or {}).get("path"))
                    if discovered
                    else inferred_test_path_for_mew_source(path)
                )
                if paired_test_path and not any(
                    str(existing).replace("\\", "/").startswith("tests/") for existing in target_paths
                ):
                    target_paths.append(paired_test_path)
            memory["target_paths"] = target_paths[:5]
        memory["latest_tool_call_id"] = stale_call.get("id")
        memory["latest_tool_state"] = format_work_tool_observation_state(stale_call)
        memory["stale_after_tool_call_id"] = stale_call.get("id")
        memory["stale_after_tool"] = stale_call.get("tool") or "unknown"
    return memory


def build_working_memory(turns, calls, task=None):
    turns = list(turns or [])
    calls = list(calls or [])
    verification_state = latest_work_verification_state(calls, task=task)
    for reversed_index, turn in enumerate(reversed(turns)):
        decision_plan = turn.get("decision_plan") or {}
        action_plan = turn.get("action_plan") or {}
        for source, plan in (("think", decision_plan), ("act", action_plan)):
            memory = _normalize_working_memory(
                plan.get("working_memory") if isinstance(plan, dict) else {},
                turn=turn,
                verification_state=verification_state,
                source=source,
            )
            if memory:
                if reversed_index:
                    memory["stale_after_model_turn_id"] = turn.get("id")
                    memory["latest_model_turn_id"] = turns[-1].get("id")
                    memory["stale_turns"] = reversed_index
                return _annotate_working_memory_with_latest_tool(memory, turn, calls)

    latest_turn = turns[-1] if turns else {}
    if not latest_turn and not verification_state:
        return {}
    if not latest_turn and verification_state.get("status") == "not_run":
        return {}
    action = latest_turn.get("action") or {}
    raw = {
        "hypothesis": latest_turn.get("finished_note")
        or latest_turn.get("summary")
        or latest_turn.get("error")
        or "",
        "next_step": action.get("reason") or action.get("summary") or "",
        "open_questions": [action.get("question")] if action.get("type") == "ask_user" and action.get("question") else [],
    }
    memory = _normalize_working_memory(raw, turn=latest_turn or None, verification_state=verification_state, source="fallback")
    return _annotate_working_memory_with_latest_tool(memory, latest_turn or None, calls)


def _suppress_resolved_approval_memory(memory, calls, pending_approvals):
    if not memory or pending_approvals:
        return memory
    next_step = str(memory.get("next_step") or "").lower()
    if not (APPROVAL_WAIT_RE.search(next_step) or "承認待" in next_step or "却下待" in next_step):
        return memory
    for call in reversed(calls or []):
        if call.get("tool") not in ("write_file", "edit_file"):
            continue
        if call.get("approval_status") not in RESOLVED_APPROVAL_MEMORY_STATUSES:
            continue
        result = call.get("result") or {}
        if not result.get("dry_run"):
            continue
        status = call.get("approval_status")
        resolved = dict(memory)
        resolved["next_step"] = ""
        resolved["resolved_pending_approval"] = True
        resolved["resolved_pending_approval_tool_call_id"] = call.get("id")
        resolved["resolved_pending_approval_status"] = status
        resolved["resolved_pending_approval_state"] = f"pending approval already {status}; no pending approvals remain"
        return resolved
    return memory


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


def _duration_seconds(started_at, finished_at):
    start = parse_time(started_at)
    end = parse_time(finished_at)
    if not start or not end:
        return None
    try:
        return max(0.0, (end - start).total_seconds())
    except TypeError:
        return None


def _round_seconds(value):
    if value is None:
        return None
    return round(float(value), 1)


def _status_counts(items):
    counts = {"total": 0, "completed": 0, "failed": 0, "interrupted": 0, "running": 0}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        counts["total"] += 1
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _sum_observed_seconds(items, reference_time):
    total = 0.0
    known = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        finished_at = item.get("finished_at")
        if not finished_at and item.get("status") == "running":
            finished_at = reference_time
        seconds = _duration_seconds(item.get("started_at"), finished_at)
        if seconds is None:
            continue
        total += seconds
        known += 1
    return total, known


def _intervals_for_items(items, reference_time):
    intervals = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        finished_at = item.get("finished_at")
        if not finished_at and item.get("status") == "running":
            finished_at = reference_time
        start = parse_time(item.get("started_at"))
        end = parse_time(finished_at)
        if not start or not end:
            continue
        try:
            if end < start:
                continue
        except TypeError:
            continue
        intervals.append((start, end))
    return intervals


def _union_interval_seconds(intervals):
    normalized = sorted(intervals or [], key=lambda item: item[0])
    if not normalized:
        return 0.0
    merged = []
    current_start, current_end = normalized[0]
    for start, end in normalized[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        merged.append((current_start, current_end))
        current_start, current_end = start, end
    merged.append((current_start, current_end))
    return sum(max(0.0, (end - start).total_seconds()) for start, end in merged)


def _work_effort_reference_time(session, current_time):
    if parse_time(current_time):
        return current_time
    if (session or {}).get("status") == "active":
        return now_iso()
    return (session or {}).get("updated_at") or now_iso()


def build_work_session_effort(session, *, current_time=None, step_budget=WORK_SESSION_STEP_BUDGET):
    if not session:
        return {}
    calls = list(session.get("tool_calls") or [])
    turns = list(session.get("model_turns") or [])
    reference_time = _work_effort_reference_time(session, current_time)
    tool_counts = _status_counts(calls)
    turn_counts = _status_counts(turns)
    effective_tool_failures = sum(
        1
        for call in calls
        if isinstance(call, dict)
        and (call.get("status") in ("failed", "interrupted") or bool(work_tool_failure_record(call)))
    )
    tool_seconds, tool_seconds_known = _sum_observed_seconds(calls, reference_time)
    model_seconds, model_seconds_known = _sum_observed_seconds(turns, reference_time)
    active_seconds = _union_interval_seconds(
        _intervals_for_items(calls, reference_time) + _intervals_for_items(turns, reference_time)
    )
    wall_seconds = _duration_seconds(session.get("created_at"), reference_time)
    steps_used = tool_counts["total"] + turn_counts["total"]
    budget = max(1, int(step_budget or WORK_SESSION_STEP_BUDGET))
    remaining = max(0, budget - steps_used)
    ratio = steps_used / budget
    failure_count = effective_tool_failures + turn_counts["failed"] + turn_counts["interrupted"]
    warnings = []
    if steps_used >= budget:
        warnings.append("step_budget_exhausted")
    elif ratio >= WORK_SESSION_NEAR_STEP_RATIO:
        warnings.append("step_budget_near")
    if failure_count >= WORK_SESSION_FAILURE_HIGH_COUNT:
        warnings.append("failure_budget_exhausted")
    elif failure_count >= WORK_SESSION_FAILURE_NEAR_COUNT:
        warnings.append("failure_budget_near")
    if wall_seconds is not None:
        if wall_seconds >= WORK_SESSION_WALL_HIGH_SECONDS:
            warnings.append("wall_time_high")
        elif wall_seconds >= WORK_SESSION_WALL_NEAR_SECONDS:
            warnings.append("wall_time_near")

    if any(reason in warnings for reason in ("step_budget_exhausted", "failure_budget_exhausted", "wall_time_high")):
        pressure = "high"
        recommendation = "summarize current state and replan before continuing"
    elif warnings:
        pressure = "medium"
        recommendation = "continue, but prefer a narrow next action and refresh working memory soon"
    else:
        pressure = "low"
        recommendation = "continue"

    step_status = "over_limit" if steps_used >= budget else "near_limit" if ratio >= WORK_SESSION_NEAR_STEP_RATIO else "ok"
    return {
        "pressure": pressure,
        "warnings": warnings,
        "recommendation": recommendation,
        "steps": {
            "used": steps_used,
            "budget": budget,
            "remaining": remaining,
            "ratio": round(ratio, 2),
            "status": step_status,
        },
        "tool_calls": tool_counts,
        "model_turns": turn_counts,
        "failures": failure_count,
        "effective_tool_failures": effective_tool_failures,
        "wall_elapsed_seconds": _round_seconds(wall_seconds),
        "tool_seconds": _round_seconds(tool_seconds),
        "model_seconds": _round_seconds(model_seconds),
        "observed_active_seconds": _round_seconds(active_seconds),
        "observed_duration_counts": {
            "tool_calls": tool_seconds_known,
            "model_turns": model_seconds_known,
        },
    }


def format_work_effort_brief(effort):
    if not effort:
        return ""
    steps = effort.get("steps") or {}
    used = steps.get("used")
    budget = steps.get("budget")
    pressure = effort.get("pressure") or "unknown"
    failures = effort.get("failures")
    if used is None or budget is None:
        return f"effort={pressure}"
    return f"effort={pressure} steps={used}/{budget} failures={failures or 0}"


def _continuity_axis(key, ok, reason, artifacts=None):
    return {
        "key": key,
        "ok": bool(ok),
        "reason": reason,
        "artifacts": [artifact for artifact in (artifacts or []) if artifact],
    }


def _approval_has_visible_control(approval):
    if not approval:
        return False
    has_identity = approval.get("tool_call_id") is not None and bool(approval.get("path") or approval.get("tool"))
    has_review = bool(approval.get("diff_preview") or approval.get("diff"))
    has_decision = bool(
        approval.get("approve_hint")
        or approval.get("cli_approve_hint")
        or approval.get("approval_blocked_reason")
        or approval.get("override_approve_hint")
        or approval.get("cli_override_approve_hint")
    ) and bool(approval.get("reject_hint") or approval.get("cli_reject_hint"))
    return has_identity and has_review and has_decision


def _continuity_text_has_command_control(text):
    text = str(text or "").strip()
    if not text:
        return False
    return bool(
        re.search(r"(^|\s)(?:\./)?mew\s+", text)
        or re.search(r"(^|\s)/(?:continue|work-session)\b", text)
    )


def _continuity_text_has_runnable_action(text):
    text = str(text or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    if re.match(r"^(wait|waiting|pending)\b", lowered):
        return False
    if _continuity_text_has_command_control(text):
        return True
    return bool(re.search(r"\b(approve|reject|retry|inspect|recover|resume|review|run|continue)\b", lowered))


def _continuity_next_action_runnable(resume):
    next_action = str((resume or {}).get("next_action") or "").strip()
    if not next_action:
        return False
    approvals = (resume or {}).get("pending_approvals") or []
    if approvals:
        return all(_approval_has_visible_control(approval) for approval in approvals)
    recovery = (resume or {}).get("recovery_plan") or {}
    if recovery:
        for item in recovery.get("items") or []:
            if _continuity_recovery_item_has_control(item):
                return True
        return _continuity_text_has_runnable_action(recovery.get("next_action"))
    waiting_phases = {"running_tool", "planning", "stop_requested"}
    if (resume or {}).get("phase") in waiting_phases and "wait" in next_action:
        return True
    return _continuity_text_has_runnable_action(next_action)


def _continuity_failure_visible(failure):
    if not failure or failure.get("tool_call_id") is None:
        return False
    return bool(
        failure.get("error")
        or failure.get("summary")
        or failure.get("exit_code") is not None
        or failure.get("suggested_safe_reobserve")
    )


def _continuity_recovery_item_visible(item):
    if not item:
        return False
    has_id = item.get("tool_call_id") is not None or item.get("model_turn_id") is not None
    return has_id and bool(item.get("action")) and bool(item.get("reason") or item.get("source_error") or item.get("source_summary"))


def _continuity_recovery_item_has_control(item):
    if not item:
        return False
    hint_fields = ("hint", "auto_hint", "chat_auto_hint", "review_hint")
    has_command_hint = any(_continuity_text_has_command_control(item.get(field)) for field in hint_fields)
    return bool(has_command_hint or item.get("command") or item.get("review_steps"))


def _continuity_verification_visible(confidence):
    if not confidence:
        return False
    return bool(confidence.get("status")) and bool(
        confidence.get("reason")
        or confidence.get("command")
        or confidence.get("expected_command")
        or confidence.get("source_paths")
        or confidence.get("pending_source_paths")
    )


def _continuity_same_surface_visible(audit):
    if not audit:
        return False
    return bool(audit.get("status")) and bool(audit.get("reason") or audit.get("prompt") or audit.get("paths"))


def _continuity_recurring_failures_visible(items):
    if not items:
        return False
    return all(item.get("tool") and item.get("count") for item in items)


def _continuity_pivot_text(resume):
    pending = (resume or {}).get("pending_steer") or {}
    queued = (resume or {}).get("queued_followups") or []
    texts = []
    if str(pending.get("text") or "").strip():
        texts.append(str(pending.get("text")).strip())
    texts.extend(str(item.get("text")).strip() for item in queued if str(item.get("text") or "").strip())
    return texts


_CONTINUITY_REPAIR_ACTIONS = {
    "working_memory_survived": "refresh working memory with a hypothesis, next step, verified state, or durable planning fields like plan_items, target_paths, or open_questions",
    "risks_preserved": "inspect unresolved failures, pending approvals, and recovery state before acting",
    "next_action_runnable": "record a runnable next action, approval control, or recovery command",
    "approvals_visible": "preserve approve and reject controls for every pending approval",
    "recovery_path_visible": "record a safe recovery or reobserve path",
    "verifier_confidence_kept": "record verification status or a suggested verify command",
    "bundle_within_budget": "compact or summarize the session before continuing",
    "recent_decisions_preserved": "summarize recent decisions or older think before continuing",
    "user_pivot_preserved": "surface and handle the pending user pivot or follow-up",
}


def _continuity_recommendation(missing):
    missing = [str(item) for item in (missing or []) if item]
    if not missing:
        return {
            "summary": "continue from the preserved next action",
            "actions": [],
            "primary_axis": "",
        }
    actions = [_CONTINUITY_REPAIR_ACTIONS.get(axis, f"repair {axis}") for axis in missing]
    return {
        "summary": actions[0],
        "actions": actions,
        "primary_axis": missing[0],
    }


def build_work_continuity_score(resume):
    """Score whether a work resume can restore continuity after interruption."""
    resume = resume or {}
    memory = resume.get("working_memory") or {}
    failures = resume.get("failures") or []
    unresolved_failure = resume.get("unresolved_failure") or {}
    recovery_plan = resume.get("recovery_plan") or {}
    pending_approvals = resume.get("pending_approvals") or []
    verification_confidence = resume.get("verification_confidence") or {}
    suggested_verify = resume.get("suggested_verify_command") or {}
    context = resume.get("context") or {}
    decisions = resume.get("recent_decisions") or []
    compressed_prior = resume.get("compressed_prior_think") or {}
    notes = resume.get("notes") or []
    same_surface_audit = resume.get("same_surface_audit") or {}
    recurring_failures = resume.get("recurring_failures") or []
    pivot_texts = _continuity_pivot_text(resume)

    memory_ok = bool(
        memory.get("hypothesis")
        or memory.get("next_step")
        or memory.get("last_verified_state")
        or memory.get("plan_items")
        or memory.get("target_paths")
        or memory.get("open_questions")
    )
    risky = bool(
        unresolved_failure
        or failures
        or recovery_plan
        or pending_approvals
        or (verification_confidence and verification_confidence.get("status") != "verified")
        or same_surface_audit
        or recurring_failures
    )
    risk_checks = []
    if pending_approvals:
        risk_checks.append(all(_approval_has_visible_control(approval) for approval in pending_approvals))
    if unresolved_failure or failures:
        visible_failures = [unresolved_failure] if unresolved_failure else []
        visible_failures.extend(failures)
        risk_checks.append(any(_continuity_failure_visible(failure) for failure in visible_failures))
    if recovery_plan:
        risk_checks.append(any(_continuity_recovery_item_visible(item) for item in recovery_plan.get("items") or []))
    if verification_confidence and verification_confidence.get("status") != "verified":
        risk_checks.append(_continuity_verification_visible(verification_confidence))
    if same_surface_audit:
        risk_checks.append(_continuity_same_surface_visible(same_surface_audit))
    if recurring_failures:
        risk_checks.append(_continuity_recurring_failures_visible(recurring_failures))
    risks_ok = all(risk_checks) if risk_checks else not risky
    approvals_ok = not pending_approvals or all(_approval_has_visible_control(approval) for approval in pending_approvals)
    needs_recovery = bool(recovery_plan or unresolved_failure or failures or resume.get("phase") in ("interrupted", "failed"))
    recovery_ok = not needs_recovery or bool(
        any(_continuity_recovery_item_has_control(item) for item in recovery_plan.get("items") or [])
        or resume.get("suggested_safe_reobserve")
        or any((failure or {}).get("suggested_safe_reobserve") for failure in [unresolved_failure, *failures])
    )
    verification_needed = bool(
        pending_approvals
        or verification_confidence
        or suggested_verify
        or any((command or {}).get("tool") in ("run_tests", "verification") for command in resume.get("commands") or [])
    )
    verifier_ok = not verification_needed or bool(verification_confidence or suggested_verify or resume.get("commands"))
    context_pressure = context.get("pressure") or "unknown"
    context_ok = context_pressure in ("low", "medium") or context.get("total_session_chars") is None
    decisions_ok = bool(decisions or compressed_prior.get("items") or notes or memory)
    pivot_ok = not pivot_texts or bool(pivot_texts)

    axes = [
        _continuity_axis(
            "working_memory_survived",
            memory_ok,
            "working memory has hypothesis, next step, latest verification state, or durable planning fields"
            if memory_ok
            else "working memory is absent",
            ["working_memory"],
        ),
        _continuity_axis(
            "risks_preserved",
            risks_ok,
            "risk-bearing state is visible" if risky else "no unresolved risk detected",
            ["unresolved_failure", "failures", "recovery_plan", "verification_confidence"],
        ),
        _continuity_axis(
            "next_action_runnable",
            _continuity_next_action_runnable(resume),
            "next action has a visible command, recovery path, or approval control",
            ["next_action", "pending_approvals", "recovery_plan"],
        ),
        _continuity_axis(
            "approvals_visible",
            approvals_ok,
            "pending approvals have review and decision controls" if pending_approvals else "no pending approvals",
            ["pending_approvals"],
        ),
        _continuity_axis(
            "recovery_path_visible",
            recovery_ok,
            "recovery or failure review path is visible" if needs_recovery else "no recovery path needed",
            ["recovery_plan", "suggested_safe_reobserve", "next_action"],
        ),
        _continuity_axis(
            "verifier_confidence_kept",
            verifier_ok,
            "verification state or command history is visible"
            if verification_needed
            else "no verifier context is required yet",
            ["verification_confidence", "suggested_verify_command", "commands"],
        ),
        _continuity_axis(
            "bundle_within_budget",
            context_ok,
            f"context pressure is {context_pressure}",
            ["context"],
        ),
        _continuity_axis(
            "recent_decisions_preserved",
            decisions_ok,
            "recent decisions, compressed prior think, notes, or working memory preserve the thread"
            if decisions_ok
            else "no decisions, compressed prior think, notes, or memory are visible",
            ["recent_decisions", "compressed_prior_think", "notes", "working_memory"],
        ),
        _continuity_axis(
            "user_pivot_preserved",
            pivot_ok,
            "pending steer or queued follow-up is visible" if pivot_texts else "no user pivot is pending",
            ["pending_steer", "queued_followups"],
        ),
    ]
    passed = sum(1 for axis in axes if axis.get("ok"))
    total = len(axes)
    if passed == total:
        status = "strong"
    elif passed >= max(1, total - 2):
        status = "usable"
    elif passed >= max(1, total // 2):
        status = "weak"
    else:
        status = "broken"
    missing = [axis.get("key") for axis in axes if not axis.get("ok")]
    return {
        "status": status,
        "passed": passed,
        "total": total,
        "score": f"{passed}/{total}",
        "missing": missing,
        "recommendation": _continuity_recommendation(missing),
        "axes": axes,
    }


def format_work_continuity_inline(continuity):
    if not continuity:
        return ""
    missing = continuity.get("missing") or []
    suffix = f" missing={','.join(str(item) for item in missing)}" if missing else ""
    return f"continuity: {continuity.get('score') or '-'} status={continuity.get('status') or 'unknown'}{suffix}"


def format_work_continuity_recommendation(continuity):
    if not continuity or not (continuity.get("missing") or []):
        return ""
    recommendation = continuity.get("recommendation") or {}
    summary = str(recommendation.get("summary") or "").strip()
    return f"continuity_next: {summary}" if summary else ""


def model_turn_is_redundant_planning_churn(turn):
    turn = turn if isinstance(turn, dict) else {}
    if turn.get("tool_call_id"):
        return False
    action = turn.get("action") or {}
    action_type = action.get("type") or action.get("tool") or ""
    if action_type and action_type not in ("wait", "planning"):
        return False
    status = str(turn.get("status") or "")
    if status not in ("failed", "interrupted"):
        return False
    summary = str(turn.get("summary") or "").casefold()
    error = str(turn.get("error") or "").casefold()
    return (
        summary == "planning work step"
        or "request timed out" in error
        or "interrupted before the work model turn completed" in error
    )


def compact_model_turns_for_prompt(turns, *, max_consecutive_redundant=1):
    compacted = []
    redundant_seen = 0
    for turn in reversed(list(turns or [])):
        if model_turn_is_redundant_planning_churn(turn):
            if redundant_seen >= max(0, int(max_consecutive_redundant or 0)):
                continue
            redundant_seen += 1
        else:
            redundant_seen = 0
        compacted.append(turn)
    compacted.reverse()
    return compacted


def build_compressed_prior_think(turns, *, recent_limit=8, limit=4):
    turns = compact_model_turns_for_prompt(turns)
    recent_count = max(0, int(recent_limit or 0))
    older_turns = turns[:-recent_count] if recent_count else turns
    if not older_turns:
        return {}
    entries = []
    for turn in older_turns[-max(1, int(limit or 1)):]:
        action = turn.get("action") or {}
        plan = turn.get("decision_plan") or {}
        memory = plan.get("working_memory") if isinstance(plan, dict) else {}
        memory = memory if isinstance(memory, dict) else {}
        entry = {
            "model_turn_id": turn.get("id"),
            "status": turn.get("status") or "unknown",
            "action": action.get("type") or action.get("tool") or "unknown",
            "summary": clip_inline_text(
                turn.get("finished_note") or turn.get("summary") or turn.get("error") or "",
                240,
            ),
        }
        guidance = work_turn_guidance_snapshot(turn)
        if guidance:
            entry["guidance_snapshot"] = clip_inline_text(guidance, 240)
        for key in ("hypothesis", "next_step", "last_verified_state"):
            if memory.get(key):
                entry[key] = clip_inline_text(memory.get(key), 240)
        plan_items = _coerce_working_memory_plan_items(memory.get("plan_items") or [])
        if plan_items:
            entry["plan_items"] = plan_items
        target_paths = _coerce_working_memory_target_paths(memory.get("target_paths") or [])
        if target_paths:
            entry["target_paths"] = target_paths
        questions = memory.get("open_questions") or []
        if questions:
            entry["open_questions"] = [clip_inline_text(str(item), 160) for item in questions[:3]]
        entries.append(entry)
    return {
        "total_older_model_turns": len(older_turns),
        "shown": len(entries),
        "omitted": max(0, len(older_turns) - len(entries)),
        "items": entries,
    }


def work_session_phase(session, calls, turns, pending_approvals, active_work_todo=None):
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
    todo = active_work_todo if isinstance(active_work_todo, dict) else session.get("active_work_todo") or {}
    todo_phase = str(todo.get("status") or "").strip()
    if todo_phase in WORK_TODO_PHASE_STATUSES:
        return todo_phase
    return "idle"


def work_session_has_running_activity(session):
    if not session:
        return False
    calls = list(session.get("tool_calls") or [])
    turns = list(session.get("model_turns") or [])
    return any((call or {}).get("status") == "running" for call in calls) or any(
        (turn or {}).get("status") == "running" for turn in turns
    )


def work_session_latest_activity_at(session):
    latest_raw = ""
    latest_ts = None
    for collection in ("tool_calls", "model_turns"):
        for item in session.get(collection) or []:
            if not isinstance(item, dict):
                continue
            for key in ("finished_at", "updated_at", "started_at", "created_at"):
                raw = item.get(key)
                ts = parse_time(raw)
                if not ts:
                    continue
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                    latest_raw = raw
    if latest_raw:
        return latest_raw
    for key in ("updated_at", "created_at"):
        raw = session.get(key)
        if parse_time(raw):
            return raw
    return ""


def work_interrupted_dry_run_write_retryable(call, *, effect_classification=None):
    if (call or {}).get("tool") not in WRITE_WORK_TOOLS:
        return False
    parameters = (call or {}).get("parameters") or {}
    result = (call or {}).get("result") or {}
    effect = effect_classification or work_recovery_effect_classification(call)
    if effect != "no_action":
        return False
    if parameters.get("apply") or result.get("applied"):
        return False
    if parameters.get("approved_from_tool_call_id"):
        return False
    if (call or {}).get("approval_status") in NON_PENDING_APPROVAL_STATUSES:
        return False
    if result.get("written") and not result.get("dry_run"):
        return False
    return True


def work_write_recovery_world_state(call):
    if (call or {}).get("tool") not in WRITE_WORK_TOOLS:
        return {}
    intent = (call or {}).get("write_intent") or {}
    if not intent:
        return {}
    try:
        return classify_write_intent_world_state(intent)
    except (OSError, ValueError) as exc:
        return {
            "state": "unknown",
            "path": intent.get("path") or work_call_path(call),
            "reason": str(exc),
        }


def interrupted_apply_write_recovery_action(call, write_world_state):
    if (call or {}).get("tool") not in WRITE_WORK_TOOLS:
        return ""
    parameters = (call or {}).get("parameters") or {}
    if not parameters.get("apply"):
        return ""
    state = (write_world_state or {}).get("state")
    if state == "not_started":
        return "retry_apply_write"
    if state == "completed_externally":
        return "verify_completed_write"
    return ""


def build_work_recovery_plan(session, calls, turns, limit=8):
    items = []
    task_id = (session or {}).get("task_id")
    task_arg = f" {task_id}" if task_id is not None else ""
    active_work_todo = _normalize_active_work_todo((session or {}).get("active_work_todo") or {})
    interrupted_tool_ids = {
        call.get("id")
        for call in calls
        if call.get("status") == "interrupted" and not call.get("recovery_status")
    }
    latest_retryable_tool_id = None
    latest_verification_tool_id = None
    for call in calls:
        if call.get("status") != "interrupted" or call.get("recovery_status"):
            continue
        if call.get("tool") in READ_ONLY_WORK_TOOLS or call.get("tool") in GIT_WORK_TOOLS:
            latest_retryable_tool_id = call.get("id")
        if call.get("tool") == "run_tests":
            result = call.get("result") or {}
            parameters = call.get("parameters") or {}
            if result.get("command") or parameters.get("command"):
                latest_verification_tool_id = call.get("id")
    for call in calls:
        effect_classification = work_recovery_effect_classification(call)
        rollback_review_needed = (
            call.get("status") == "failed"
            and not call.get("recovery_status")
            and call.get("tool") in WRITE_WORK_TOOLS
            and effect_classification == "rollback_needed"
        )
        command_review_needed = (
            call.get("tool") == "run_command"
            and not call.get("recovery_status")
            and (call.get("status") == "failed" or bool(work_tool_failure_record(call)))
        )
        if (
            call.get("status") != "interrupted"
            and not rollback_review_needed
            and not command_review_needed
        ) or call.get("recovery_status"):
            continue
        tool = call.get("tool") or "unknown"
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        path = work_call_path(call)
        command = result.get("command") or parameters.get("command") or ""
        if tool in WRITE_WORK_TOOLS:
            verification = result.get("verification") or {}
            command = (
                command
                or verification.get("command")
                or result.get("verification_command")
                or parameters.get("verify_command")
                or ""
            )
        write_world_state = work_write_recovery_world_state(call)
        if tool in READ_ONLY_WORK_TOOLS or tool in GIT_WORK_TOOLS:
            action = "retry_tool"
            safety = "read_only"
            reason = "interrupted read/git inspection can be retried after verifying read roots"
            review_steps = []
        elif tool in WRITE_WORK_TOOLS:
            if rollback_review_needed:
                action = "needs_user_review"
                safety = "write"
                reason = "write verification failed and rollback was not confirmed; inspect the target before continuing"
                review_steps = [
                    "open the resume with live world state",
                    "inspect git status/diff and the touched path before retrying",
                    "restore or intentionally keep the written content, then rerun the verifier",
                ]
            else:
                apply_write_action = interrupted_apply_write_recovery_action(call, write_world_state)
                if apply_write_action == "retry_apply_write":
                    action = "retry_apply_write"
                    safety = "write_resume"
                    effect_classification = "not_started"
                    reason = "interrupted apply-write can be resumed because the target still matches the pre-write state"
                    review_steps = []
                elif apply_write_action == "verify_completed_write":
                    action = "verify_completed_write"
                    safety = "write_verify"
                    effect_classification = "completed_externally"
                    reason = "interrupted apply-write already reached the intended file content; skip the write and verify"
                    review_steps = []
                elif work_interrupted_dry_run_write_retryable(call, effect_classification=effect_classification):
                    action = "retry_dry_run_write"
                    safety = "dry_run_write"
                    reason = "interrupted dry-run write preview can be retried after checking write roots"
                    review_steps = []
                else:
                    action = "needs_user_review"
                    safety = "write"
                    if write_world_state.get("state") == "partial":
                        effect_classification = "partial"
                        reason = "interrupted write left an atomic temp file; cleanup or rollback needs user review"
                    elif write_world_state.get("state") == "target_diverged":
                        effect_classification = "target_diverged"
                        reason = "interrupted write target diverged from both pre-write and intended hashes"
                    else:
                        reason = "interrupted write must be reviewed before retry or rollback"
                    review_steps = [
                        "open the resume with live world state",
                        "inspect git status/diff and the touched path before retrying",
                        "retry or re-apply only after the verifier is known",
                    ]
        elif tool == "run_tests" and command:
            action = "retry_verification"
            safety = "verification"
            reason = "interrupted verifier can be rerun with the same explicit verification command after checking world state"
            review_steps = []
        elif tool in COMMAND_WORK_TOOLS:
            action = "needs_user_review"
            safety = "command"
            reason = (
                "command failed after execution; review recorded stdout/stderr before rerunning side-effecting work"
                if command_review_needed
                else "interrupted command or verification may have side effects"
            )
            review_steps = [
                "open the resume with live world state",
                "read captured stdout/stderr if present",
                "rerun only if the command is idempotent or the user approves",
            ]
        else:
            action = "needs_user_review"
            safety = "unknown"
            reason = "interrupted tool type is not automatically recoverable"
            review_steps = ["open the resume with live world state before retrying"]
        item = {
            "kind": "tool_call",
            "tool_call_id": call.get("id"),
            "tool": tool,
            "action": action,
            "safety": safety,
            "effect_classification": effect_classification,
            "reason": reason,
            "source_summary": call.get("summary") or "",
            "source_error": call.get("error") or "",
            "recovery_hint": call.get("recovery_hint") or "",
        }
        if write_world_state:
            item["write_world_state"] = write_world_state
        if action == "retry_tool" and call.get("id") == latest_retryable_tool_id:
            read_root = work_recovery_read_root(call)
            read_arg = shlex.quote(read_root)
            item["hint"] = f"{mew_executable()} work{task_arg} --recover-session --allow-read {read_arg}"
            item["auto_hint"] = (
                f"{mew_executable()} work{task_arg} --session --resume --allow-read {read_arg} --auto-recover-safe"
            )
            item["chat_auto_hint"] = f"/work-session resume{task_arg} --allow-read {read_arg} --auto-recover-safe"
            if path:
                item["path"] = path
        if action == "retry_verification" and call.get("id") == latest_verification_tool_id:
            read_root = work_recovery_read_root(call)
            read_arg = shlex.quote(read_root)
            command_arg = shlex.quote(command)
            item["hint"] = (
                f"{mew_executable()} work{task_arg} --recover-session --allow-read {read_arg} "
                f"--allow-verify --verify-command {command_arg}"
            )
            item["command"] = command
        if action == "retry_dry_run_write":
            write_root = work_recovery_read_root(call)
            write_arg = shlex.quote(write_root)
            item["hint"] = f"{mew_executable()} work{task_arg} --recover-session --allow-write {write_arg}"
            item["auto_hint"] = (
                f"{mew_executable()} work{task_arg} --session --resume --allow-write {write_arg} "
                f"--auto-recover-safe"
            )
            item["chat_auto_hint"] = f"/work-session resume{task_arg} --allow-write {write_arg} --auto-recover-safe"
            if path:
                item["path"] = path
        if action == "retry_apply_write":
            write_root = work_recovery_read_root(call)
            write_arg = shlex.quote(write_root)
            verify_command = parameters.get("verify_command") or (call.get("write_intent") or {}).get("verify_command") or ""
            item["hint"] = f"{mew_executable()} work{task_arg} --recover-session --allow-write {write_arg}"
            if verify_command:
                item["hint"] += f" --allow-verify --verify-command {shlex.quote(verify_command)}"
                item["command"] = verify_command
            if path:
                item["path"] = path
        if action == "verify_completed_write":
            read_root = work_recovery_read_root(call)
            read_arg = shlex.quote(read_root)
            verify_command = parameters.get("verify_command") or (call.get("write_intent") or {}).get("verify_command") or ""
            item["hint"] = f"{mew_executable()} work{task_arg} --recover-session --allow-read {read_arg}"
            if verify_command:
                item["hint"] += f" --allow-verify --verify-command {shlex.quote(verify_command)}"
                item["command"] = verify_command
            if path:
                item["path"] = path
        if action == "needs_user_review":
            review_arg = shlex.quote(work_recovery_read_root(call))
            item["review_hint"] = f"{mew_executable()} work{task_arg} --session --resume --allow-read {review_arg}"
            item["review_steps"] = review_steps
            if path:
                item["path"] = path
            if command:
                item["command"] = command
            if tool in COMMAND_WORK_TOOLS:
                running_output = call.get("running_output") or {}
                cwd = result.get("cwd") or parameters.get("cwd")
                if cwd:
                    item["cwd"] = cwd
                if "exit_code" in result:
                    item["exit_code"] = result.get("exit_code")
                stdout_tail = clip_tail(
                    result.get("stdout") or running_output.get("stdout") or "",
                    DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS,
                )
                stderr_tail = clip_tail(
                    result.get("stderr") or running_output.get("stderr") or "",
                    DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS,
                )
                if stdout_tail:
                    item["stdout_tail"] = stdout_tail
                if stderr_tail:
                    item["stderr_tail"] = stderr_tail
        items.append(item)

    for turn in turns:
        if (turn.get("status") not in {"interrupted", "failed"}) or turn.get("recovery_status"):
            continue
        if turn.get("status") in {"interrupted", "failed"}:
            timeout_recovery_turn_plan_item = _timeout_before_draft_model_recovery_plan_item(
                active_work_todo,
                turn=turn,
                task_id=task_id,
                fallback_turn_id=session.get("last_model_turn_id"),
            )
            if timeout_recovery_turn_plan_item:
                timeout_turn_id = timeout_recovery_turn_plan_item.get("model_turn_id")
                already_has_timeout_recovery = any(
                    item.get("action") == _RESUME_DRAFT_FROM_CACHED_WINDOWS_ACTION
                    and item.get("model_turn_id") == timeout_turn_id
                    for item in items
                )
                if not already_has_timeout_recovery:
                    items.append(timeout_recovery_turn_plan_item)
                continue
        if turn.get("status") != "interrupted":
            continue
        if turn.get("tool_call_id") in interrupted_tool_ids:
            continue
        items.append(
            {
                "kind": "model_turn",
                "model_turn_id": turn.get("id"),
                "action": "replan",
                "safety": "no_tool_started",
                "effect_classification": "no_action",
                "reason": "interrupted model planning has no committed tool result; verify world state and run a new work step",
                "source_summary": turn.get("summary") or "",
                "source_error": turn.get("error") or "",
                "recovery_hint": turn.get("recovery_hint") or "",
                "hint": f"{mew_executable()} work{task_arg} --live --allow-read <path>",
            }
        )

    items = items[-limit:]
    if not items:
        return {}
    if any(item.get("action") == "needs_user_review" for item in items):
        next_action = "verify the world and review side-effecting work before retry"
    elif any(item.get("action") == "verify_completed_write" for item in items):
        next_action = "skip the already-completed write, then rerun the recorded verifier"
    elif any(item.get("action") == "retry_apply_write" for item in items):
        next_action = "verify the world, then resume the interrupted write with explicit write and verify gates"
    elif any(item.get("action") == "retry_tool" for item in items):
        next_action = "verify the world, then retry recoverable interrupted read/git tool after checking read roots"
    elif any(item.get("action") == "retry_dry_run_write" for item in items):
        next_action = "verify the world, then retry interrupted dry-run write preview after checking write roots"
    elif any(item.get("action") == "retry_verification" for item in items):
        next_action = "verify the world, then rerun the interrupted verifier with the same explicit command"
    elif any(item.get("action") == "resume_draft_from_cached_windows" for item in items):
        next_action = (
            "resume the write-ready draft using the exact cached window frontier before retrying"
        )
    else:
        next_action = "verify world state and replan the interrupted model step"
    return {"next_action": next_action, "items": items}


def _tiny_write_ready_draft_recovery_plan_item(
    blocker_todo,
    *,
    tiny_turn=None,
    task_id=None,
    fallback_turn_id=None,
):
    todo = _normalize_active_work_todo(blocker_todo) if blocker_todo else {}
    if todo.get("status") != "blocked_on_patch":
        return {}
    blocker = todo.get("blocker") if isinstance(todo.get("blocker"), dict) else {}
    if not blocker:
        return {}
    task_arg = f" {task_id}" if task_id is not None else ""
    blocker_code = str(blocker.get("code") or "").strip()
    detail = str(blocker.get("detail") or "").strip()
    model_turn_id = (tiny_turn or {}).get("id") or fallback_turn_id
    item = {
        "kind": "model_turn",
        "model_turn_id": model_turn_id,
        "action": "needs_user_review",
        "safety": "read_only",
        "effect_classification": "unknown",
        "reason": (
            f"tiny draft blocker {blocker_code or 'unknown'}; {detail or 'refresh the cached windows or todo source before retrying'}"
        ).strip(),
        "source_summary": detail or f"tiny draft blocker: {blocker_code}",
        "source_error": "",
        "review_hint": f"{mew_executable()} work{task_arg} --session --resume --allow-read . --auto-recover-safe",
        "hint": f"{mew_executable()} work{task_arg} --session --resume --allow-read . --auto-recover-safe",
        "review_steps": [
            "open the resume with live world state",
            "refresh cached windows or target source before retrying the tiny-lane draft",
            "retry the edit-ready draft lane",
        ],
    }
    return item


def _normalize_active_work_todo_cached_window_roots(active_work_todo):
    roots = []
    seen = set()
    for window in (active_work_todo or {}).get("cached_window_refs") or []:
        if not isinstance(window, dict):
            continue
        path = str(window.get("path") or "").strip()
        if not path or path in seen:
            continue
        roots.append(path)
        seen.add(path)
    if roots:
        return roots
    source = (active_work_todo or {}).get("source") or {}
    for path in source.get("target_paths") or []:
        candidate = str(path or "").strip()
        if not candidate or candidate in seen:
            continue
        roots.append(candidate)
        seen.add(candidate)
    return roots


def _contains_timeout_signal(*parts):
    for part in parts:
        candidate = str(part or "").strip().lower()
        if "timeout" in candidate or "timed out" in candidate:
            return True
    return False


def _is_write_ready_timeout_candidate_turn(turn):
    if not isinstance(turn, dict):
        return False
    metrics = turn.get("model_metrics") or {}
    if str(metrics.get("draft_phase") or "").strip() != "write_ready":
        return False
    if str(metrics.get("tiny_write_ready_draft_outcome") or "").strip():
        return False
    if not bool(metrics.get("write_ready_fast_path")):
        return False
    if _coerce_non_negative_int(metrics.get("cached_window_ref_count"), 0) <= 0:
        return False
    status = str(turn.get("status") or "").strip()
    if status == "interrupted":
        return True
    if status != "failed":
        return False
    if _contains_timeout_signal(str(turn.get("summary") or ""), str(turn.get("error") or "")):
        return True
    think = metrics.get("think") or {}
    if _contains_timeout_signal(str(think.get("termination_reason") or ""), str(think.get("timeout_reason") or "")):
        return True
    if _contains_timeout_signal(str((turn.get("action") or {}).get("type") or ""), str((turn.get("action") or {}).get("reason") or "")):
        return True
    error = turn.get("error")
    if isinstance(error, dict):
        if _contains_timeout_signal(
            error.get("code"),
            error.get("name"),
            error.get("type"),
            error.get("reason"),
            error.get("message"),
        ):
            return True
    if isinstance(think.get("timeout_seconds"), (int, float)):
        if _contains_timeout_signal(str(think.get("timeout_reason") or "")):
            return True
        return False
    failure_bits = f"{turn.get('summary') or ''} {turn.get('error') or ''}"
    return _contains_timeout_signal(failure_bits)


def _timeout_before_draft_model_recovery_plan_item(
    active_work_todo,
    *,
    turn,
    task_id=None,
    fallback_turn_id=None,
):
    todo = _normalize_active_work_todo(active_work_todo)
    if todo.get("status") != "blocked_on_patch":
        return {}
    if not todo.get("cached_window_refs"):
        return {}
    if not _is_write_ready_timeout_candidate_turn(turn):
        return {}
    task_arg = f" {task_id}" if task_id is not None else ""
    read_roots = _normalize_active_work_todo_cached_window_roots(todo)
    if not read_roots:
        read_roots = ["."]
    parts = [mew_executable(), "work", task_arg.strip(), "--session", "--resume"]
    for root in read_roots:
        parts.extend(["--allow-read", shlex.quote(root)])
    parts.append("--auto-recover-safe")
    command = " ".join(part for part in parts if part)
    model_turn_id = (turn or {}).get("id") or fallback_turn_id
    return {
        "kind": "model_turn",
        "model_turn_id": model_turn_id,
        "action": _RESUME_DRAFT_FROM_CACHED_WINDOWS_ACTION,
        "safety": "read_only",
        "effect_classification": "unknown",
        "active_work_todo_id": todo.get("id") or "",
        "cached_window_refs": list(todo.get("cached_window_refs") or []),
        "reason": (
            "write-ready draft was interrupted/failed before emitting any edits; "
            "resume with the exact cached window frontier before retrying"
        ),
        "source_summary": str((turn or {}).get("summary") or "write-ready draft timeout before edits"),
        "source_error": str((turn or {}).get("error") or ""),
        "hint": command,
        "review_hint": command,
        "review_steps": [
            "open the resume with live world state",
            "refresh the exact cached window frontier before retrying",
            "resume the write-ready draft with the same exact windows",
        ],
    }


def _append_unique_recovery_plan_item(recovery_plan, item):
    if not item:
        return recovery_plan
    recovery_plan = recovery_plan if isinstance(recovery_plan, dict) else {}
    items = list(recovery_plan.get("items") or [])
    for existing in items:
        if existing.get("action") == item.get("action") and (
            existing.get("model_turn_id") == item.get("model_turn_id")
            or existing.get("tool_call_id") == item.get("tool_call_id")
        ):
            return recovery_plan
    items.append(item)
    recovery_plan["items"] = items[-8:]
    if not recovery_plan.get("next_action"):
        recovery_plan["next_action"] = str(item.get("reason") or "resolve the tiny-lane draft blocker and retry")
    return recovery_plan


def work_recovery_effect_classification(call):
    tool = (call or {}).get("tool") or ""
    parameters = (call or {}).get("parameters") or {}
    result = (call or {}).get("result") or {}
    if tool in READ_ONLY_WORK_TOOLS or tool in GIT_WORK_TOOLS:
        return "no_action"
    if tool == "run_tests":
        return "verify_pending"
    if tool == "run_command":
        return "action_committed"
    if tool in WRITE_WORK_TOOLS:
        verification = result.get("verification") or {}
        verification_failed = "exit_code" in verification and verification.get("exit_code") != 0
        if verification_failed and not result.get("rolled_back"):
            return "rollback_needed"
        apply_requested = bool(parameters.get("apply") or result.get("applied"))
        write_attempted = bool(result.get("written") and not result.get("dry_run"))
        verify_expected = bool(parameters.get("verify_command") or result.get("verification_command"))
        if (apply_requested or write_attempted) and verify_expected and not verification:
            return "verify_pending"
        if apply_requested or write_attempted:
            return "write_started"
        return "no_action"
    if tool in COMMAND_WORK_TOOLS:
        return "action_committed"
    return "unknown"


def select_work_recovery_plan_item(recovery_plan):
    items = list((recovery_plan or {}).get("items") or [])
    if not items:
        return {}
    for action in RECOVERY_PLAN_ACTION_PRIORITY:
        matches = [item for item in items if item.get("action") == action]
        if matches:
            if action == "needs_user_review":
                best = {}
                best_priority = len(WORK_RECOVERY_EFFECT_PRIORITY)
                for item in matches:
                    effect = item.get("effect_classification") or "unknown"
                    try:
                        priority = WORK_RECOVERY_EFFECT_PRIORITY.index(effect)
                    except ValueError:
                        priority = len(WORK_RECOVERY_EFFECT_PRIORITY)
                    if priority <= best_priority:
                        best = item
                        best_priority = priority
                return best
            return matches[-1]
    return items[-1]


def _hash_value(value):
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()


def _cached_window_signature(window):
    if not isinstance(window, dict):
        return ""
    return (
        "sha1:"
        + _hash_value(
            f"{window.get('path')}|{window.get('line_start')}|{window.get('line_end')}|{window.get('text') or ''}"
        )
    )


def _write_ready_draft_metrics(model_turns):
    draft_attempts = 0
    latest_draft_metrics = None
    for turn in (model_turns or []):
        metrics = turn.get("model_metrics") or {}
        if bool(metrics.get("write_ready_fast_path")):
            draft_attempts += 1
            latest_draft_metrics = metrics
    return draft_attempts, latest_draft_metrics


def _normalize_active_work_todo(todo):
    if not isinstance(todo, dict):
        return {}
    status = str(todo.get("status") or "").strip()
    if status and status not in WORK_TODO_STATUSES:
        return {}
    source = todo.get("source") if isinstance(todo.get("source"), dict) else {}
    cached_window_refs = []
    for item in todo.get("cached_window_refs") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        try:
            line_start = int(item.get("line_start") or 0)
            line_end = int(item.get("line_end") or 0)
        except (TypeError, ValueError):
            continue
        if not path or line_start <= 0 or line_end <= 0:
            continue
        cached_window_refs.append(
            {
                "path": path,
                "tool_call_id": item.get("tool_call_id"),
                "line_start": line_start,
                "line_end": line_end,
                "context_truncated": bool(item.get("context_truncated")),
                "window_sha1": str(item.get("window_sha1") or "").strip(),
            }
        )
    attempts = todo.get("attempts") if isinstance(todo.get("attempts"), dict) else {}
    normalized = {
        "id": str(todo.get("id") or "").strip(),
        "status": status,
        "source": {
            "plan_item": str(source.get("plan_item") or "").strip(),
            "target_paths": _coerce_working_memory_target_paths(source.get("target_paths") or []),
            "verify_command": str(source.get("verify_command") or "").strip(),
        },
        "cached_window_refs": cached_window_refs,
        "attempts": {
            "draft": max(0, int(attempts.get("draft") or 0)),
            "review": max(0, int(attempts.get("review") or 0)),
        },
        "patch_draft_id": str(todo.get("patch_draft_id") or "").strip(),
        "blocker": dict(todo.get("blocker") or {}),
        "created_at": str(todo.get("created_at") or "").strip(),
        "updated_at": str(todo.get("updated_at") or "").strip(),
    }
    if not normalized["id"] and not normalized["status"] and not normalized["source"]["plan_item"]:
        return {}
    return normalized


def _active_work_todo_frontier_key(todo):
    todo = _normalize_active_work_todo(todo)
    source = todo.get("source") or {}
    return (
        source.get("plan_item") or "",
        tuple(source.get("target_paths") or []),
    )


def _cached_window_ref_from_observation(window):
    window = window if isinstance(window, dict) else {}
    path = str(window.get("path") or "").strip()
    try:
        line_start = int(window.get("line_start") or 0)
        line_end = int(window.get("line_end") or 0)
    except (TypeError, ValueError):
        return {}
    if not path or line_start <= 0 or line_end <= 0:
        return {}
    cached_window_ref = {
        "path": path,
        "tool_call_id": window.get("tool_call_id"),
        "line_start": line_start,
        "line_end": line_end,
        "context_truncated": bool(window.get("context_truncated")),
    }
    window_sha1 = str(window.get("window_sha1") or "").strip() or _cached_window_signature(window)
    if window_sha1:
        cached_window_ref["window_sha1"] = window_sha1
    return cached_window_ref


def _next_active_work_todo_id(session):
    ordinal = int(session.get("last_work_todo_ordinal") or 0) + 1
    session["last_work_todo_ordinal"] = ordinal
    session_id = session.get("id")
    if session_id is None:
        return f"todo-{ordinal}"
    return f"todo-{session_id}-{ordinal}"


def _build_active_work_todo_candidate(
    *,
    target_paths,
    cached_window_by_path,
    first_observation,
    verify_command,
    model_turns,
    current_time=None,
):
    if not first_observation.get("edit_ready"):
        return {}

    relevant_target_paths = _relevant_resume_target_paths(target_paths)
    cached_window_refs = []
    for target_path in relevant_target_paths:
        cached_window_ref = _cached_window_ref_from_observation(cached_window_by_path.get(target_path) or {})
        if cached_window_ref:
            cached_window_refs.append(cached_window_ref)
    if not relevant_target_paths or len(cached_window_refs) != len(relevant_target_paths):
        return {}

    draft_attempts, _latest_metrics = _write_ready_draft_metrics(model_turns)
    return {
        "id": "",
        "status": "drafting",
        "source": {
            "plan_item": str(first_observation.get("plan_item") or "").strip(),
            "target_paths": relevant_target_paths,
            "verify_command": str(verify_command or "").strip(),
        },
        "cached_window_refs": cached_window_refs,
        "attempts": {"draft": draft_attempts, "review": 0},
        "patch_draft_id": "",
        "blocker": {},
        "created_at": current_time,
        "updated_at": current_time,
    }


def _observe_active_work_todo(
    session,
    *,
    plan_item_observations,
    target_paths,
    cached_window_by_path,
    verify_command,
    model_turns,
    current_time=None,
):
    current_time = current_time or session.get("updated_at") or now_iso()
    existing = _normalize_active_work_todo(session.get("active_work_todo") or {})
    first_observation = (plan_item_observations or [{}])[0] if plan_item_observations else {}
    candidate = _build_active_work_todo_candidate(
        target_paths=target_paths,
        cached_window_by_path=cached_window_by_path,
        first_observation=first_observation,
        verify_command=verify_command,
        model_turns=model_turns,
        current_time=current_time,
    )
    if not candidate:
        return {}
    if not existing:
        candidate["id"] = _next_active_work_todo_id(session)
        latest_tiny_turn = _latest_tiny_write_ready_draft_turn(
            model_turns,
            todo_id=candidate["id"],
        )
        candidate = _apply_tiny_write_ready_draft_outcome_to_active_work_todo(
            candidate,
            turn=latest_tiny_turn,
            todo_id=candidate["id"],
            current_time=current_time,
        )
        session["active_work_todo"] = _normalize_active_work_todo(candidate)
        return session["active_work_todo"]
    if _active_work_todo_frontier_key(existing) != _active_work_todo_frontier_key(candidate):
        candidate["id"] = _next_active_work_todo_id(session)
        latest_tiny_turn = _latest_tiny_write_ready_draft_turn(
            model_turns,
            todo_id=candidate["id"],
        )
        candidate = _apply_tiny_write_ready_draft_outcome_to_active_work_todo(
            candidate,
            turn=latest_tiny_turn,
            todo_id=candidate["id"],
            current_time=current_time,
        )
        session["active_work_todo"] = _normalize_active_work_todo(candidate)
        return session["active_work_todo"]

    updated = dict(existing)
    updated["source"] = candidate["source"]
    updated["cached_window_refs"] = candidate["cached_window_refs"]
    updated["updated_at"] = current_time
    updated.setdefault("created_at", candidate["created_at"])
    updated["attempts"] = {
        "draft": max(
            (existing.get("attempts") or {}).get("draft") or 0,
            (candidate.get("attempts") or {}).get("draft") or 0,
        ),
        "review": max((existing.get("attempts") or {}).get("review") or 0, 0),
    }
    if not updated.get("status"):
        updated["status"] = "drafting"
    latest_tiny_turn = _latest_tiny_write_ready_draft_turn(
        model_turns,
        todo_id=updated.get("id"),
    )
    updated = _apply_tiny_write_ready_draft_outcome_to_active_work_todo(
        updated,
        turn=latest_tiny_turn,
        todo_id=updated.get("id"),
        current_time=current_time,
    )
    normalized_updated = _normalize_active_work_todo(updated)
    if normalized_updated != existing:
        session["active_work_todo"] = normalized_updated
        return normalized_updated
    return existing


def _build_draft_state_from_turns(model_turns, plan_item_observations, active_work_todo=None):
    draft_state = {
        "draft_phase": "",
        "draft_attempts": 0,
        "cached_window_ref_count": 0,
        "cached_window_hashes": [],
        "draft_runtime_mode": "",
        "draft_prompt_contract_version": "",
        "draft_prompt_static_chars": None,
        "draft_prompt_dynamic_chars": None,
        "draft_retry_same_prefix": False,
    }
    draft_attempts, latest_draft_metrics = _write_ready_draft_metrics(model_turns)
    draft_state["draft_attempts"] = draft_attempts
    if latest_draft_metrics:
        draft_state["draft_runtime_mode"] = latest_draft_metrics.get("draft_runtime_mode") or ""
        draft_state["draft_prompt_contract_version"] = (
            latest_draft_metrics.get("draft_prompt_contract_version") or ""
        )
        draft_state["draft_prompt_static_chars"] = latest_draft_metrics.get("draft_prompt_static_chars")
        draft_state["draft_prompt_dynamic_chars"] = latest_draft_metrics.get("draft_prompt_dynamic_chars")
        draft_state["draft_retry_same_prefix"] = bool(latest_draft_metrics.get("draft_retry_same_prefix"))
    active_work_todo = _normalize_active_work_todo(active_work_todo)
    if active_work_todo:
        cached_window_refs = active_work_todo.get("cached_window_refs") or []
        draft_state["draft_phase"] = active_work_todo.get("status") or ""
        draft_state["draft_attempts"] = max(
            draft_state["draft_attempts"],
            (active_work_todo.get("attempts") or {}).get("draft") or 0,
        )
        draft_state["cached_window_ref_count"] = len(cached_window_refs)
        draft_state["cached_window_hashes"] = [
            item.get("window_sha1") or ""
            for item in cached_window_refs
            if item.get("window_sha1")
        ]
        return draft_state
    if latest_draft_metrics:
        draft_state["draft_phase"] = latest_draft_metrics.get("draft_phase") or "write_ready"
        draft_state["cached_window_ref_count"] = latest_draft_metrics.get("cached_window_ref_count") or 0
        draft_state["cached_window_hashes"] = latest_draft_metrics.get("cached_window_hashes") or []
        return draft_state
    if not plan_item_observations:
        return draft_state
    first_observation = plan_item_observations[0]
    if first_observation.get("edit_ready"):
        cached_windows = first_observation.get("cached_windows") or []
        draft_state["draft_phase"] = "write_ready"
        draft_state["cached_window_ref_count"] = len(cached_windows)
        draft_state["cached_window_hashes"] = [
            _cached_window_signature(item) for item in cached_windows
        ]
    return draft_state


def build_work_session_resume(session, task=None, limit=8, state=None, current_time=None):
    if not session:
        return None
    calls = list(session.get("tool_calls") or [])
    turns = list(session.get("model_turns") or [])
    default_options = (session or {}).get("default_options") or {}
    if default_options.get("verify_disabled"):
        verify_command = ""
    else:
        verify_command = default_options.get("verify_command") or latest_work_verify_command(calls, task=task)
    verify_command_hint = shlex.quote(verify_command) if verify_command else '"<command>"'
    declared_write_roots = list(default_options.get("allow_write") or [])
    paths = []
    commands = []
    failures = []
    pending_approvals = []
    latest_safe_reobserve = {}
    task_id = session.get("task_id") or (task or {}).get("id")

    def work_task_command(*parts):
        command_parts = ["work"]
        if task_id:
            command_parts.append(task_id)
        command_parts.extend(parts)
        return mew_command(*command_parts)

    for call in calls:
        path = work_call_path(call)
        if path and path not in paths:
            paths.append(path)

        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        if call.get("tool") in COMMAND_WORK_TOOLS:
            running_output = call.get("running_output") or {}
            command_record = {
                "tool_call_id": call.get("id"),
                "tool": call.get("tool"),
                "command": result.get("command") or parameters.get("command"),
                "cwd": result.get("cwd") or parameters.get("cwd"),
                "exit_code": result.get("exit_code"),
                "stdout": clip_tail(
                    result.get("stdout") or running_output.get("stdout") or "",
                    DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS,
                ),
                "stderr": clip_tail(
                    result.get("stderr") or running_output.get("stderr") or "",
                    DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS,
                ),
            }
            if running_output:
                command_record.update(
                    {
                        "status": call.get("status"),
                        "output_running": call.get("status") == "running",
                        "output_updated_at": running_output.get("updated_at") or "",
                        "output_max_chars": running_output.get("max_chars") or DEFAULT_RUNNING_OUTPUT_MAX_CHARS,
                        "stdout_truncated": bool(running_output.get("stdout_truncated")),
                        "stderr_truncated": bool(running_output.get("stderr_truncated")),
                    }
                )
            commands.append(command_record)
        verification = result.get("verification") or {}
        if verification:
            commands.append(
                {
                    "tool_call_id": call.get("id"),
                    "tool": "verification",
                    "command": verification.get("command"),
                    "cwd": verification.get("cwd"),
                    "exit_code": verification.get("exit_code"),
                    "stdout": clip_tail(verification.get("stdout") or "", DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS),
                    "stderr": clip_tail(verification.get("stderr") or "", DEFAULT_RESUME_COMMAND_OUTPUT_MAX_CHARS),
                }
            )

        failure_record = work_tool_failure_record(call)
        if call.get("status") in ("failed", "interrupted") or failure_record:
            safe_reobserve = suggested_safe_reobserve_for_call(call, calls=calls)
            failure = {
                "tool_call_id": call.get("id"),
                "tool": call.get("tool"),
                "error": call.get("error") or "",
                "summary": call.get("summary") or "",
                "exit_code": (failure_record or result).get("exit_code"),
                "recovery_status": call.get("recovery_status") or "",
                "recovered_by_tool_call_id": call.get("recovered_by_tool_call_id"),
            }
            if safe_reobserve:
                failure["suggested_safe_reobserve"] = safe_reobserve
                latest_safe_reobserve = safe_reobserve
            failures.append(failure)

        if (
            call.get("tool") in WRITE_WORK_TOOLS
            and result.get("dry_run")
            and result.get("changed")
            and call.get("approval_status") not in NON_PENDING_APPROVAL_STATUSES
        ):
            tool_call_id = call.get("id")
            write_path = path or "."
            diff = result.get("diff") or ""
            diff_stats = _result_diff_stats(result, diff)
            approval_diff, diff_truncated = clipped_approval_diff(diff)
            pairing_status = work_write_pairing_status(session, call)
            approval = {
                "tool_call_id": tool_call_id,
                "tool": call.get("tool"),
                "path": path,
                "summary": call.get("summary") or "",
                "approval_status": call.get("approval_status") or "",
                "approval_error": call.get("approval_error") or "",
                "diff_stats": diff_stats,
                "diff_preview": format_diff_preview(diff, max_chars=1200, diff_stats=diff_stats),
                "diff": approval_diff,
                "diff_truncated": diff_truncated,
                "diff_max_chars": DEFAULT_RESUME_APPROVAL_DIFF_MAX_CHARS,
                "approve_hint": (
                    f"/work-session approve {tool_call_id} --allow-write {shlex.quote(write_path)} "
                    f"--allow-verify --verify-command {verify_command_hint}"
                ),
                "defer_verify_hint": (
                    f"/work-session approve {tool_call_id} --allow-write {shlex.quote(write_path)} --defer-verify"
                ),
                "reject_hint": f"/work-session reject {tool_call_id} <reason>",
                "cli_approve_hint": work_task_command(
                    "--approve-tool",
                    tool_call_id,
                    "--allow-write",
                    write_path,
                    "--allow-verify",
                    "--verify-command",
                    verify_command or "<command>",
                ),
                "cli_defer_verify_hint": work_task_command(
                    "--approve-tool",
                    tool_call_id,
                    "--allow-write",
                    write_path,
                    "--defer-verify",
                ),
                "cli_reject_hint": work_task_command("--reject-tool", tool_call_id, "--reject-reason", "<reason>"),
            }
            auto_defer_reason = work_approval_default_defer_reason(call)
            if auto_defer_reason:
                approval["auto_defer_verify_reason"] = auto_defer_reason
                approval["verify_now_hint"] = approval["approve_hint"]
                approval["cli_verify_now_hint"] = approval["cli_approve_hint"]
                approval["approve_hint"] = approval["defer_verify_hint"]
                approval["cli_approve_hint"] = approval["cli_defer_verify_hint"]
            if pairing_status:
                approval["pairing_status"] = pairing_status
                if pairing_status.get("status") == "missing_test_edit":
                    blocked_approve_hint = approval["approve_hint"]
                    cli_blocked_approve_hint = approval["cli_approve_hint"]
                    approval["approval_blocked_reason"] = (
                        "add a paired tests/** write/edit before approving this src/mew source edit"
                    )
                    approval["blocked_approve_hint"] = blocked_approve_hint
                    approval["cli_blocked_approve_hint"] = cli_blocked_approve_hint
                    approval["override_approve_hint"] = f"{blocked_approve_hint} --allow-unpaired-source-edit"
                    approval["cli_override_approve_hint"] = f"{cli_blocked_approve_hint} --allow-unpaired-source-edit"
                    approval["approve_hint"] = ""
                    approval["cli_approve_hint"] = ""
                    approval["defer_verify_hint"] = ""
                    approval["cli_defer_verify_hint"] = ""
            pending_approvals.append(approval)

    approve_all_hint = ""
    cli_approve_all_hint = ""
    approve_all_blocked_reason = ""
    blocked_approve_all_hint = ""
    cli_blocked_approve_all_hint = ""
    override_approve_all_hint = ""
    cli_override_approve_all_hint = ""
    if len(pending_approvals) > 1:
        write_paths = []
        for approval in pending_approvals:
            write_path = approval.get("path") or "."
            if write_path not in write_paths:
                write_paths.append(write_path)
        write_flags = " ".join(f"--allow-write {shlex.quote(write_path)}" for write_path in write_paths)
        approve_all_hint = (
            f"/work-session approve all {write_flags} "
            f"--allow-verify --verify-command {verify_command_hint}"
        )
        cli_approve_all_parts = ["--approve-all"]
        for write_path in write_paths:
            cli_approve_all_parts.extend(["--allow-write", write_path])
        cli_approve_all_parts.extend(["--allow-verify", "--verify-command", verify_command or "<command>"])
        cli_approve_all_hint = work_task_command(*cli_approve_all_parts)
        governance_approval = None
        from .self_improve_audit import _m5_governance_path_category

        for approval in pending_approvals:
            approval_path = approval.get("path") or "."
            category = _m5_governance_path_category(approval_path)
            if category:
                governance_approval = (category, approval_path)
                break
        if governance_approval:
            category, approval_path = governance_approval
            approve_all_blocked_reason = (
                "approve-all is blocked for pending governance/policy dry-run edits; "
                f"approve each tool explicitly instead ({category} {approval_path})"
            )
            blocked_approve_all_hint = approve_all_hint
            cli_blocked_approve_all_hint = cli_approve_all_hint
            approve_all_hint = ""
            cli_approve_all_hint = ""
        elif any((approval.get("pairing_status") or {}).get("status") == "missing_test_edit" for approval in pending_approvals):
            approve_all_blocked_reason = (
                "one or more src/mew source edits need paired tests/** write/edit before approve-all"
            )
            blocked_approve_all_hint = approve_all_hint
            cli_blocked_approve_all_hint = cli_approve_all_hint
            override_approve_all_hint = f"{approve_all_hint} --allow-unpaired-source-edit"
            cli_override_approve_all_hint = f"{cli_approve_all_hint} --allow-unpaired-source-edit"
            approve_all_hint = ""
            cli_approve_all_hint = ""

    suggested_verify_command = suggested_verify_command_for_calls(calls)
    verification_coverage_warning = verification_coverage_warning_for_calls(calls, task=task)

    turns_for_prompt = compact_model_turns_for_prompt(turns)
    recent_decisions = []
    for turn in turns_for_prompt[-limit:]:
        action = turn.get("action") or {}
        plan = turn.get("decision_plan") or {}
        memory = plan.get("working_memory") if isinstance(plan, dict) else {}
        memory = memory if isinstance(memory, dict) else {}
        recent_decisions.append(
            {
                "model_turn_id": turn.get("id"),
                "status": turn.get("status"),
                "action": action.get("type") or action.get("tool") or "unknown",
                "summary": turn.get("finished_note") or turn.get("summary") or turn.get("error") or "",
                "guidance_snapshot": clip_inline_text(work_turn_guidance_snapshot(turn), 240),
                "tool_call_id": turn.get("tool_call_id"),
                "plan_items": _coerce_working_memory_plan_items(memory.get("plan_items") or []),
                "target_paths": _coerce_working_memory_target_paths(memory.get("target_paths") or []),
                "open_questions": [clip_inline_text(str(item), 160) for item in (memory.get("open_questions") or [])[:3]],
                "last_verified_state": clip_inline_text(str(memory.get("last_verified_state") or ""), 240),
            }
        )
    compressed_prior_think = build_compressed_prior_think(turns_for_prompt, recent_limit=limit, limit=4)

    latest_call = calls[-1] if calls else None
    latest_failed = bool(
        latest_call
        and (
            latest_call.get("status") in ("failed", "interrupted")
            or work_tool_failure_record(latest_call)
        )
    )

    queued_followups = [
        dict(item)
        for item in (session.get("queued_followups") or [])
        if item.get("status") == "queued" and str(item.get("text") or "").strip()
    ]
    recovery_plan = build_work_recovery_plan(session, calls, turns, limit=limit)
    working_memory = _suppress_resolved_approval_memory(
        build_working_memory(turns, calls, task=task),
        calls,
        pending_approvals,
    )
    if not working_memory and isinstance(session.get("startup_memory"), dict):
        working_memory = dict(session.get("startup_memory") or {})
    target_path_cached_window_observations = []
    cached_window_by_path = {}
    adjacent_read_observations = build_adjacent_read_observations(calls, limit=3)
    target_paths = _coerce_working_memory_target_paths((working_memory or {}).get("target_paths") or [])
    relevant_target_paths = _relevant_resume_target_paths(target_paths)
    if relevant_target_paths:
        for target_path in relevant_target_paths:
            for call in reversed(calls):
                if call.get("tool") != "read_file" or call.get("status") != "completed":
                    continue
                result = call.get("result") or {}
                read_path = work_call_path(call) or result.get("path") or ""
                if not read_path or not str(read_path).endswith(target_path):
                    continue
                line_start = result.get("line_start")
                line_end = result.get("line_end")
                if not isinstance(line_start, int) or not isinstance(line_end, int):
                    continue
                observation = {
                    "path": target_path,
                    "tool_call_id": call.get("id"),
                    "line_start": line_start,
                    "line_end": line_end,
                    "reason": f"recent read_file window already covered {target_path}:{line_start}-{line_end}",
                    "context_truncated": bool(result.get("context_truncated")),
                }
                for adjacent in reversed(adjacent_read_observations):
                    adjacent_path = str(adjacent.get("path") or "")
                    if adjacent.get("last_tool_call_id") != call.get("id"):
                        continue
                    if adjacent.get("context_truncated"):
                        continue
                    if not adjacent_path or not (
                        adjacent_path.endswith(target_path) or str(read_path).endswith(adjacent_path)
                    ):
                        continue
                    merged_line_start = adjacent.get("merged_line_start")
                    merged_line_end = adjacent.get("merged_line_end")
                    if not isinstance(merged_line_start, int) or not isinstance(merged_line_end, int):
                        continue
                    observation["line_start"] = merged_line_start
                    observation["line_end"] = merged_line_end
                    observation["reason"] = (
                        f"merged adjacent read_file windows already covered {target_path}:{merged_line_start}-{merged_line_end}"
                    )
                    break
                target_path_cached_window_observations.append(observation)
                cached_window_by_path[target_path] = {
                    **observation,
                    "text": result.get("text") or "",
                }
                break
    demoted_adjacent_read_observations = []
    plan_item_observations = []
    plan_items = _coerce_working_memory_plan_items((working_memory or {}).get("plan_items") or [])
    actionable_plan_item = ""
    skipped_exact_read_plan_items = []
    if plan_items:
        actionable_plan_item, skipped_exact_read_plan_items = first_actionable_plan_item(
            plan_items,
            target_path_cached_window_observations,
        )
    if actionable_plan_item:
        plan_item_observation = {
            "plan_item": actionable_plan_item,
            "reason": "first remaining working_memory.plan_items entry preserved from the latest THINK turn",
        }
        requested_window = plan_item_exact_read_window(actionable_plan_item)
        if requested_window:
            plan_item_observation["requested_window"] = requested_window
        relevant_target_paths = _relevant_resume_target_paths(target_paths)
        if relevant_target_paths:
            primary_target_path = relevant_target_paths[0]
            plan_item_observation["target_path"] = primary_target_path
            cached_window = cached_window_by_path.get(primary_target_path)
            if cached_window:
                plan_item_observation["cached_window"] = {
                    "tool_call_id": cached_window.get("tool_call_id"),
                    "line_start": cached_window.get("line_start"),
                    "line_end": cached_window.get("line_end"),
                    "context_truncated": cached_window.get("context_truncated"),
                }
                plan_item_observation["reason"] = (
                    f"first remaining plan item paired to target path {primary_target_path} and its recent cached window"
                )
            else:
                plan_item_observation["reason"] = (
                    f"first remaining plan item paired to target path {primary_target_path} from working_memory.target_paths"
                )
            cached_windows = []
            for target_path in relevant_target_paths:
                cached_window = cached_window_by_path.get(target_path)
                if not cached_window:
                    continue
                cached_windows.append(
                    {
                        "path": target_path,
                        "tool_call_id": cached_window.get("tool_call_id"),
                        "line_start": cached_window.get("line_start"),
                        "line_end": cached_window.get("line_end"),
                        "context_truncated": cached_window.get("context_truncated"),
                    }
                )
            if cached_windows:
                plan_item_observation["cached_windows"] = cached_windows
            edit_ready = bool(relevant_target_paths) and len(cached_windows) == len(relevant_target_paths) and all(
                not item.get("context_truncated") for item in cached_windows
            )
            if edit_ready and requested_window:
                requested_window_covered = any(
                    cached_window_covers_exact_read(cached_window, requested_window)
                    for cached_window in cached_windows
                )
                if not requested_window_covered:
                    edit_ready = False
                    plan_item_observation["reason"] = (
                        "first remaining plan item still needs an uncached exact read window "
                        f"{requested_window['path']}:{requested_window['line_start']}-{requested_window['line_end']}"
                    )
            plan_item_observation["edit_ready"] = edit_ready
            if edit_ready:
                plan_item_observation["reason"] = (
                    "first remaining plan item is paired to fully cached target paths and is ready for one edit batch"
                )
        plan_item_observations.append(plan_item_observation)
    if plan_item_observations and plan_item_observations[0].get("edit_ready"):
        edit_ready_paths = {
            str(item.get("path") or "")
            for item in (plan_item_observations[0].get("cached_windows") or [])
            if str(item.get("path") or "").strip()
        }
        kept_adjacent_read_observations = []
        for observation in adjacent_read_observations:
            observation_path = str(observation.get("path") or "")
            if any(observation_path.endswith(path) for path in edit_ready_paths):
                demoted = dict(observation)
                demoted["reason"] = (
                    f"{observation.get('reason')} edit_ready is true for this paired target path, so the reread signal is demoted behind the pending edit batch"
                )
                demoted_adjacent_read_observations.append(demoted)
                continue
            kept_adjacent_read_observations.append(observation)
        adjacent_read_observations = kept_adjacent_read_observations
    active_work_todo = _observe_active_work_todo(
        session,
        plan_item_observations=plan_item_observations,
        target_paths=target_paths,
        cached_window_by_path=cached_window_by_path,
        verify_command=verify_command,
        model_turns=turns,
        current_time=current_time,
    )
    latest_tiny_turn = _latest_tiny_write_ready_draft_turn(
        turns,
        todo_id=(active_work_todo or {}).get("id"),
    )
    recovery_plan = _append_unique_recovery_plan_item(
        recovery_plan,
        _tiny_write_ready_draft_recovery_plan_item(
            active_work_todo,
            tiny_turn=latest_tiny_turn,
            task_id=task_id,
            fallback_turn_id=session.get("last_model_turn_id"),
        ),
    )
    draft_state = _build_draft_state_from_turns(turns, plan_item_observations, active_work_todo=active_work_todo)
    phase = work_session_phase(session, calls, turns, pending_approvals, active_work_todo=active_work_todo)

    if session.get("status") == "closed":
        if task_id and task and task.get("status") == "done":
            reopen_command = mew_command("task", "update", task_id, "--status", "ready")
            next_action = (
                "review this closed work session; "
                f"task #{task_id} is done, so reopen it before starting a new one with {reopen_command}"
            )
        elif task_id:
            start_command = mew_command("work", task_id, "--start-session")
            next_action = f"review this closed work session or start a new one with {start_command}"
        else:
            start_command = mew_command("work", "--start-session")
            next_action = f"review this closed work session or start a new one with {start_command}"
    elif phase == "stop_requested":
        if session.get("stop_action") == "interrupt_submit":
            if work_session_has_running_activity(session):
                next_action = "interrupt-submit requested; wait for the running step to reach a boundary"
            else:
                if task_id:
                    live_command = work_session_runtime_command(session, task_id)
                else:
                    live_command = work_session_runtime_command(session, None)
                next_action = f"continue to submit pending interrupt with /continue in chat or {live_command}"
        else:
            if work_session_has_running_activity(session):
                next_action = "stop requested; the running work loop should pause at the next boundary"
            else:
                if task_id:
                    resume_command = mew_command("work", task_id, "--session", "--resume", "--allow-read", ".")
                else:
                    resume_command = mew_command("work", "--session", "--resume", "--allow-read", ".")
                next_action = f"work session is paused; resume only when needed with {resume_command}"
    elif pending_approvals:
        next_action = "approve or reject pending write tool calls"
    elif phase == "running_tool":
        next_action = f"wait for the running work tool, or run {mew_command('repair')} if the process died"
    elif phase == "planning":
        next_action = f"wait for the running work model turn, or run {mew_command('repair')} if the process died"
    elif phase == "interrupted":
        next_action = "inspect interrupted work state, verify the world, then retry or choose a new action"
    elif phase == "drafting":
        next_action = "draft one bounded patch from the cached paired windows or record one exact blocker"
    elif phase == "blocked_on_patch":
        next_action = "inspect the active patch blocker and refresh the exact cached windows or todo source before retrying"
    elif latest_failed:
        next_action = "inspect the latest failure and decide whether to retry, edit, or ask the user"
    else:
        if task_id:
            live_command = work_session_runtime_command(session, task_id)
        else:
            live_command = work_session_runtime_command(session, None)
        next_action = f"continue the work session with /continue in chat or {live_command}"

    if recovery_plan.get("next_action") and phase in ("interrupted", "idle", "failed"):
        next_action = recovery_plan["next_action"]
    if phase == "idle":
        next_action = refresh_stale_memory_next_action(next_action, working_memory)
    repair_anchor_observations = build_repair_anchor_observations(
        session,
        calls,
        failures,
        working_memory=working_memory,
        limit=4,
    )
    user_preferences = build_work_user_preferences(state, limit=limit)
    active_memory = build_work_active_memory(session=session, task=task, limit=limit)
    effort = build_work_session_effort(session, current_time=current_time)
    same_surface_audit = build_same_surface_audit_checkpoint(session, task, calls)
    verification_confidence = verification_confidence_checkpoint_for_calls(calls, task=task)

    resume = {
        "session_id": session.get("id"),
        "task_id": session.get("task_id"),
        "status": session.get("status"),
        "title": session.get("title") or (task or {}).get("title") or "",
        "goal": session.get("goal") or "",
        "phase": phase,
        "updated_at": session.get("updated_at"),
        "active_work_todo": active_work_todo or {},
        "draft_phase": draft_state.get("draft_phase") or "",
        "draft_attempts": draft_state.get("draft_attempts", 0),
        "cached_window_ref_count": draft_state.get("cached_window_ref_count", 0),
        "cached_window_hashes": draft_state.get("cached_window_hashes") or [],
        "draft_runtime_mode": draft_state.get("draft_runtime_mode") or "",
        "draft_prompt_contract_version": draft_state.get("draft_prompt_contract_version") or "",
        "draft_prompt_static_chars": draft_state.get("draft_prompt_static_chars"),
        "draft_prompt_dynamic_chars": draft_state.get("draft_prompt_dynamic_chars"),
        "draft_retry_same_prefix": bool(draft_state.get("draft_retry_same_prefix")),
        "files_touched": paths[-limit:],
        "declared_write_roots": declared_write_roots,
        "commands": commands[-limit:],
        "suggested_verify_command": suggested_verify_command,
        "verification_coverage_warning": verification_coverage_warning,
        "verification_confidence": verification_confidence,
        "failures": failures[-limit:],
        "unresolved_failure": latest_unresolved_failure(failures),
        "recurring_failures": build_recurring_work_failures(calls, limit=3),
        "low_yield_observations": build_low_yield_observation_warnings(calls, limit=3),
        "redundant_search_observations": build_redundant_search_observations(calls, limit=3),
        "adjacent_read_observations": adjacent_read_observations,
        "demoted_adjacent_read_observations": demoted_adjacent_read_observations,
        "target_path_cached_window_observations": target_path_cached_window_observations,
        "plan_item_observations": plan_item_observations,
        "skipped_exact_read_plan_items": skipped_exact_read_plan_items,
        "repair_anchor_observations": repair_anchor_observations,
        "pending_approvals": pending_approvals[-limit:],
        "pending_steer": session.get("pending_steer") or {},
        "queued_followups": queued_followups[:limit],
        "queued_followups_total": len(queued_followups),
        "queued_followups_truncated": len(queued_followups) > limit,
        "approve_all_hint": approve_all_hint,
        "cli_approve_all_hint": cli_approve_all_hint,
        "approve_all_blocked_reason": approve_all_blocked_reason,
        "blocked_approve_all_hint": blocked_approve_all_hint if approve_all_blocked_reason else "",
        "cli_blocked_approve_all_hint": cli_blocked_approve_all_hint if approve_all_blocked_reason else "",
        "override_approve_all_hint": override_approve_all_hint,
        "cli_override_approve_all_hint": cli_override_approve_all_hint,
        "notes": list(session.get("notes") or [])[-limit:],
        "recent_decisions": recent_decisions,
        "compressed_prior_think": compressed_prior_think,
        "working_memory": working_memory,
        "user_preferences": user_preferences,
        "active_memory": active_memory,
        "same_surface_audit": same_surface_audit,
        "effort": effort,
        "context": build_work_context_metrics(calls, turns),
        "stop_request": (
            {
                "requested_at": session.get("stop_requested_at"),
                "reason": session.get("stop_reason") or "stop requested",
                "action": session.get("stop_action") or "",
                "submit_text": session.get("stop_submit_text") or "",
            }
            if session.get("stop_requested_at")
            else {}
        ),
        "last_stop_request": session.get("last_stop_request") or {},
        "recovery_plan": recovery_plan,
        "suggested_safe_reobserve": latest_safe_reobserve,
        "next_action": next_action,
    }
    resume["continuity"] = build_work_continuity_score(resume)
    return resume


def recovery_next_action_with_world_state(next_action, world_state):
    next_action = str(next_action or "").strip()
    if not next_action:
        return ""
    world_state = world_state if isinstance(world_state, dict) else {}
    git_status = world_state.get("git_status") if isinstance(world_state.get("git_status"), dict) else {}
    files = list(world_state.get("files") or [])
    missing_paths = [record.get("path") or "(unknown path)" for record in files if record.get("exists") is False]
    if missing_paths:
        return f"{next_action}; first inspect missing touched paths: {', '.join(missing_paths[:2])}"

    git_known = git_status.get("exit_code") == 0
    git_clean = git_known and not (git_status.get("stdout") or "").strip() and not (
        git_status.get("stderr") or ""
    ).strip()
    if files and git_clean:
        return f"{next_action}; live world check: git is clean and observed paths still exist"
    if files or git_status:
        return f"{next_action}; live world check: review git status and observed paths before retrying"
    return next_action


def refresh_stale_memory_next_action(next_action, working_memory):
    if not working_memory or not working_memory.get("stale_after_tool_call_id"):
        return next_action
    latest_tool = working_memory.get("stale_after_tool") or "tool"
    prefix = f"refresh working memory from latest {latest_tool} result"
    if next_action:
        return f"{prefix}, then {next_action}"
    return prefix


def attach_work_resume_world_state(resume, world_state):
    if not resume:
        return resume
    resume["world_state"] = world_state or {}
    recovery_plan = resume.get("recovery_plan") or {}
    if recovery_plan.get("next_action") and resume.get("phase") in ("interrupted", "idle", "failed"):
        resume["next_action"] = recovery_next_action_with_world_state(
            recovery_plan.get("next_action"),
            resume.get("world_state"),
        )
    return resume


def format_work_session_resume(resume):
    if not resume:
        return "No active work session."
    lines = [
        f"Work resume #{resume.get('session_id')} [{resume.get('status')}] task=#{resume.get('task_id')}",
        f"title: {resume.get('title') or ''}",
        f"phase: {resume.get('phase') or 'unknown'}",
        f"updated_at: {resume.get('updated_at')}",
    ]
    active_work_todo = resume.get("active_work_todo") or {}
    if active_work_todo:
        lines.append(
            "active_work_todo: "
            f"id={active_work_todo.get('id') or ''} "
            f"status={active_work_todo.get('status') or ''} "
            f"draft_attempts={(active_work_todo.get('attempts') or {}).get('draft', 0)}"
        )
        todo_source = active_work_todo.get("source") or {}
        if todo_source.get("plan_item"):
            lines.append(f"active_work_todo_plan_item: {todo_source.get('plan_item')}")
    continuity_text = format_work_continuity_inline(resume.get("continuity") or {})
    if continuity_text:
        lines.append(continuity_text)
    continuity_next = format_work_continuity_recommendation(resume.get("continuity") or {})
    if continuity_next:
        lines.append(continuity_next)
    lines.extend(["", "Files touched"])
    files = resume.get("files_touched") or []
    if files:
        lines.extend(f"- {path}" for path in files)
    else:
        lines.append("(none)")

    lines.extend(["", "Declared write roots"])
    declared_write_roots = resume.get("declared_write_roots") or []
    if declared_write_roots:
        lines.extend(f"- {path}" for path in declared_write_roots)
    else:
        lines.append("(none)")

    lines.extend(["", "Commands"])
    commands = resume.get("commands") or []
    if commands:
        for command in commands:
            lines.append(
                f"#{command.get('tool_call_id')} {command.get('tool')} "
                f"exit={format_exit_code(command.get('exit_code'))} {command.get('command') or ''}"
            )
            if command.get("stdout"):
                lines.append("  stdout:")
                for output_line in command.get("stdout", "").splitlines() or [""]:
                    lines.append(f"    {output_line}")
            if command.get("stderr"):
                lines.append("  stderr:")
                for output_line in command.get("stderr", "").splitlines() or [""]:
                    lines.append(f"    {output_line}")
    else:
        lines.append("(none)")

    suggested_verify = resume.get("suggested_verify_command") or {}
    if suggested_verify:
        lines.extend(["", "Suggested verification"])
        lines.append(f"command: {suggested_verify.get('command')}")
        lines.append(f"source: {suggested_verify.get('source_path')}")
        lines.append(f"test: {suggested_verify.get('test_path')}")
        if suggested_verify.get("reason"):
            lines.append(f"reason: {suggested_verify.get('reason')}")

    coverage_warning = resume.get("verification_coverage_warning") or {}
    if coverage_warning:
        lines.extend(["", "Verification coverage warning"])
        lines.append(f"command: {coverage_warning.get('command')}")
        lines.append(f"source: {coverage_warning.get('source_path')}")
        lines.append(f"expected_test: {coverage_warning.get('expected_test_path')}")
        lines.append(f"expected: {coverage_warning.get('expected_command')}")
        if coverage_warning.get("reason"):
            lines.append(f"reason: {coverage_warning.get('reason')}")

    verification_confidence = resume.get("verification_confidence") or {}
    if verification_confidence:
        lines.extend(["", "Verification confidence"])
        lines.append(
            f"status={verification_confidence.get('status')} "
            f"confidence={verification_confidence.get('confidence')}"
        )
        if verification_confidence.get("command"):
            lines.append(f"command: {verification_confidence.get('command')}")
        if verification_confidence.get("expected_command"):
            lines.append(f"expected: {verification_confidence.get('expected_command')}")
        if verification_confidence.get("source_paths"):
            lines.append(f"sources: {', '.join(str(path) for path in verification_confidence.get('source_paths') or [])}")
        if verification_confidence.get("uncovered_tests"):
            lines.append(
                f"uncovered_tests: {', '.join(str(path) for path in verification_confidence.get('uncovered_tests') or [])}"
            )
        if verification_confidence.get("pending_source_paths"):
            lines.append(
                "pending_source_paths: "
                f"{', '.join(str(path) for path in verification_confidence.get('pending_source_paths') or [])}"
            )
        if verification_confidence.get("reason"):
            lines.append(f"reason: {verification_confidence.get('reason')}")

    lines.extend(["", "Pending approvals"])
    approvals = resume.get("pending_approvals") or []
    if approvals:
        if resume.get("approve_all_blocked_reason"):
            lines.append(f"approve all blocked: {resume.get('approve_all_blocked_reason')}")
            if resume.get("override_approve_all_hint"):
                lines.append(f"override approve all: {resume.get('override_approve_all_hint')}")
        elif resume.get("approve_all_hint"):
            lines.append(f"approve all: {resume.get('approve_all_hint')}")
        for approval in approvals:
            lines.append(f"#{approval.get('tool_call_id')} {approval.get('tool')} {approval.get('path') or ''}")
            if approval.get("diff_preview"):
                lines.append("  diff:")
                for preview_line in approval.get("diff_preview", "").splitlines():
                    lines.append(f"    {preview_line}")
            if approval.get("approval_blocked_reason"):
                lines.append(f"  approve blocked: {approval.get('approval_blocked_reason')}")
                if approval.get("override_approve_hint"):
                    lines.append(f"  override approve: {approval.get('override_approve_hint')}")
            elif approval.get("approve_hint"):
                lines.append(f"  approve: {approval.get('approve_hint')}")
                if approval.get("defer_verify_hint"):
                    lines.append(f"  defer verify: {approval.get('defer_verify_hint')}")
            if approval.get("reject_hint"):
                lines.append(f"  reject: {approval.get('reject_hint')}")
            pairing = approval.get("pairing_status") or {}
            if pairing:
                lines.append(f"  pairing_status: {pairing.get('status')}")
                if pairing.get("reason"):
                    lines.append(f"  pairing_reason: {pairing.get('reason')}")
                if pairing.get("suggested_test_path"):
                    lines.append(f"  suggested_test_path: {pairing.get('suggested_test_path')}")
                if pairing.get("paired_tool_call_id") is not None:
                    lines.append(
                        f"  paired_test: #{pairing.get('paired_tool_call_id')} {pairing.get('paired_path') or ''}".rstrip()
                    )
    else:
        lines.append("(none)")

    pending_steer = resume.get("pending_steer") or {}
    if pending_steer.get("text"):
        lines.extend(["", "Pending steer"])
        source = pending_steer.get("source") or "user"
        created_at = pending_steer.get("created_at") or ""
        prefix = f"{created_at} " if created_at else ""
        lines.append(f"- {prefix}[{source}] {clip_inline_text(pending_steer.get('text'), 500)}")

    queued_followups = resume.get("queued_followups") or []
    if queued_followups:
        queued_total = int(resume.get("queued_followups_total") or len(queued_followups))
        suffix = f" (showing {len(queued_followups)} of {queued_total})" if queued_total > len(queued_followups) else ""
        lines.extend(["", f"Queued follow-ups{suffix}"])
        for item in queued_followups:
            source = item.get("source") or "user"
            created_at = item.get("created_at") or ""
            prefix = f"{created_at} " if created_at else ""
            lines.append(f"- #{item.get('id')} {prefix}[{source}] {clip_inline_text(item.get('text'), 500)}")

    lines.extend(["", "Failures"])
    failures = resume.get("failures") or []
    if failures:
        for failure in failures:
            recovered = ""
            if failure.get("recovery_status"):
                recovered = f" recovery={failure.get('recovery_status')}"
                if failure.get("recovered_by_tool_call_id") is not None:
                    recovered += f" by=#{failure.get('recovered_by_tool_call_id')}"
            lines.append(
                f"#{failure.get('tool_call_id')} {failure.get('tool')} "
                f"exit={format_exit_code(failure.get('exit_code'))}{recovered} "
                f"{failure.get('error') or failure.get('summary') or ''}"
            )
            reobserve = failure.get("suggested_safe_reobserve") or {}
            if reobserve:
                params = shlex.join(
                    f"{key}={value}" for key, value in (reobserve.get("parameters") or {}).items()
                )
                suffix = f" {params}" if params else ""
                if reobserve.get("action"):
                    lines.append(f"  reobserve: {reobserve.get('action')}{suffix}")
                else:
                    lines.append(f"  review: {reobserve.get('kind') or 'recorded_output_review'}{suffix}")
                if reobserve.get("reason"):
                    lines.append(f"  reason: {reobserve.get('reason')}")
    else:
        lines.append("(none)")

    recurring = resume.get("recurring_failures") or []
    if recurring:
        lines.extend(["", "Recurring failures"])
        for item in recurring:
            target = f" {item.get('target')}" if item.get("target") else ""
            lines.append(
                f"- {item.get('tool')}{target} failed {item.get('count')}x "
                f"(same error: {item.get('error')}); last_tool=#{item.get('last_tool_call_id')}"
            )

    low_yield = resume.get("low_yield_observations") or []
    if low_yield:
        lines.extend(["", "Low-yield observations"])
        for item in low_yield:
            target = f" {item.get('path')}" if item.get("path") else ""
            pattern = f" pattern={item.get('pattern')}" if item.get("pattern") else ""
            queries = ", ".join(str(query) for query in (item.get("queries") or [])[:5])
            lines.append(
                f"- {item.get('tool')}{target}{pattern} returned zero matches "
                f"{item.get('count')}x; last_tool=#{item.get('last_tool_call_id')}"
            )
            if queries:
                lines.append(f"  queries: {queries}")
            if item.get("suggested_next"):
                lines.append(f"  suggested_next: {item.get('suggested_next')}")

    redundant_search = resume.get("redundant_search_observations") or []
    if redundant_search:
        lines.extend(["", "Redundant search observations"])
        for item in redundant_search:
            target = f" {item.get('path')}" if item.get("path") else ""
            pattern = f" pattern={item.get('pattern')}" if item.get("pattern") else ""
            query = f" query={item.get('query')}" if item.get("query") else ""
            line = item.get("prior_first_match_line") or item.get("latest_first_match_line")
            line_text = f" first_match_line={line}" if line else ""
            lines.append(
                f"- {item.get('tool')}{target}{pattern}{query} repeated with matches "
                f"{item.get('count')}x; last_tool=#{item.get('last_tool_call_id')}{line_text}"
            )
            if item.get("suggested_next"):
                lines.append(f"  suggested_next: {item.get('suggested_next')}")

    adjacent_reads = resume.get("adjacent_read_observations") or []
    if adjacent_reads:
        lines.extend(["", "Adjacent read observations"])
        for item in adjacent_reads:
            line_range = (
                f" lines={item.get('merged_line_start')}-{item.get('merged_line_end')}"
                if item.get("merged_line_start") and item.get("merged_line_end")
                else ""
            )
            lines.append(
                f"- {item.get('tool')} {item.get('path')} repeated with adjacent windows "
                f"{item.get('count')}x; last_tool=#{item.get('last_tool_call_id')}{line_range}"
            )
            if item.get("suggested_next"):
                lines.append(f"  suggested_next: {item.get('suggested_next')}")

    plan_item_observations = resume.get("plan_item_observations") or []
    if plan_item_observations:
        lines.extend(["", "Plan item observations"])
        for item in plan_item_observations:
            target = f" target_path={item.get('target_path')}" if item.get("target_path") else ""
            edit_ready = ""
            if "edit_ready" in item:
                edit_ready = f" edit_ready={item.get('edit_ready')}"
            lines.append(f"- {item.get('plan_item') or '(unknown)'}{target}{edit_ready}")
            if item.get("reason"):
                lines.append(f"  reason: {item.get('reason')}")
            cached_window = item.get("cached_window") or {}
            if cached_window:
                lines.append(
                    "  cached_window: "
                    f"tool_call=#{cached_window.get('tool_call_id')} "
                    f"lines={cached_window.get('line_start')}-{cached_window.get('line_end')} "
                    f"truncated={bool(cached_window.get('context_truncated'))}"
                )
            cached_windows = item.get("cached_windows") or []
            if cached_windows:
                lines.append("  cached_windows:")
                for cached in cached_windows:
                    lines.append(
                        "  - "
                        f"{cached.get('path')} "
                        f"lines={cached.get('line_start')}-{cached.get('line_end')} "
                        f"tool_call=#{cached.get('tool_call_id')} "
                        f"truncated={bool(cached.get('context_truncated'))}"
                    )

    target_path_cached_windows = resume.get("target_path_cached_window_observations") or []
    if target_path_cached_windows:
        lines.extend(["", "Target path cached windows"])
        for item in target_path_cached_windows:
            lines.append(
                "- "
                f"{item.get('path')} lines={item.get('line_start')}-{item.get('line_end')} "
                f"tool_call=#{item.get('tool_call_id')} "
                f"truncated={bool(item.get('context_truncated'))}"
            )
            if item.get("reason"):
                lines.append(f"  reason: {item.get('reason')}")

    demoted_adjacent_reads = resume.get("demoted_adjacent_read_observations") or []
    if demoted_adjacent_reads:
        lines.extend(["", "Demoted adjacent read observations"])
        for item in demoted_adjacent_reads:
            line_range = (
                f" lines={item.get('merged_line_start')}-{item.get('merged_line_end')}"
                if item.get("merged_line_start") and item.get("merged_line_end")
                else ""
            )
            lines.append(
                f"- {item.get('tool')} {item.get('path')} repeated with adjacent windows "
                f"{item.get('count')}x; last_tool=#{item.get('last_tool_call_id')}{line_range}"
            )
            if item.get("reason"):
                lines.append(f"  reason: {item.get('reason')}")
            if item.get("suggested_next"):
                lines.append(f"  suggested_next: {item.get('suggested_next')}")

    repair_anchors = resume.get("repair_anchor_observations") or []
    if repair_anchors:
        lines.extend(["", "Repair anchors"])
        for anchor in repair_anchors:
            params = shlex.join(
                f"{key}={value}" for key, value in (anchor.get("parameters") or {}).items()
            )
            suffix = f" {params}" if params else ""
            lines.append(f"- {anchor.get('action') or anchor.get('kind') or 'observation'}{suffix}")
            if anchor.get("reason"):
                lines.append(f"  reason: {anchor.get('reason')}")

    lines.extend(["", "Work notes"])
    notes = resume.get("notes") or []
    if notes:
        for note in notes:
            source = note.get("source") or "note"
            lines.append(f"- {note.get('created_at') or ''} [{source}] {note.get('text') or ''}".strip())
    else:
        lines.append("(none)")

    audit = resume.get("same_surface_audit") or {}
    if audit:
        lines.extend(["", "Same-surface audit"])
        lines.append(f"status={audit.get('status')} reason={audit.get('reason')}")
        paths = audit.get("paths") or []
        if paths:
            lines.append(f"paths: {', '.join(str(path) for path in paths)}")
        if audit.get("prompt"):
            lines.append(f"prompt: {audit.get('prompt')}")

    memory = resume.get("working_memory") or {}
    if memory:
        lines.extend(["", "Working memory"])
        stale_memory = bool(memory.get("stale_after_tool_call_id") or memory.get("stale_after_model_turn_id"))
        if memory.get("hypothesis"):
            lines.append(f"hypothesis: {memory.get('hypothesis')}")
        if memory.get("next_step"):
            label = "stale_next_step" if stale_memory else "next_step"
            lines.append(f"{label}: {memory.get('next_step')}")
        plan_items = memory.get("plan_items") or []
        if plan_items:
            lines.append("plan_items:")
            lines.extend(f"- {item}" for item in plan_items)
        if memory.get("target_paths"):
            lines.append(f"target_paths: {', '.join(str(path) for path in memory.get('target_paths') or [])}")
        questions = memory.get("open_questions") or []
        if questions:
            lines.append("open_questions:")
            lines.extend(f"- {question}" for question in questions)
        if memory.get("last_verified_state"):
            lines.append(f"last_verified_state: {memory.get('last_verified_state')}")
        if memory.get("latest_tool_state"):
            lines.append(f"latest_tool_state: {memory.get('latest_tool_state')}")
        if memory.get("resolved_pending_approval_state"):
            lines.append(
                f"resolved_pending_approval: #{memory.get('resolved_pending_approval_tool_call_id')} "
                f"{memory.get('resolved_pending_approval_state')}"
            )
        source = memory.get("source") or ""
        turn_id = memory.get("model_turn_id")
        if source or turn_id:
            source_text = f"source: {source}" if source else "source:"
            if turn_id:
                source_text += f" model_turn=#{turn_id}"
            lines.append(source_text)
        if memory.get("stale_after_model_turn_id"):
            lines.append(
                f"stale_after_model_turn: #{memory.get('stale_after_model_turn_id')} "
                f"({memory.get('stale_turns')} later turn(s) without working_memory; "
                f"latest=#{memory.get('latest_model_turn_id')})"
            )
        if memory.get("stale_after_tool_call_id"):
            lines.append(
                f"stale_after_tool_call: #{memory.get('stale_after_tool_call_id')} "
                f"({memory.get('stale_after_tool')} ran after this memory; refresh before relying on next_step)"
            )

    preferences = resume.get("user_preferences") or {}
    preference_items = preferences.get("items") or []
    if preference_items:
        lines.extend(["", "User preferences"])
        for preference in preference_items:
            lines.append(f"- {preference}")
        if preferences.get("truncated"):
            lines.append(f"... {preferences.get('total')} total preferences; older items omitted")

    active_memory = resume.get("active_memory") or {}
    active_memory_items = active_memory.get("items") or []
    if active_memory_items:
        lines.extend(["", "Active memory"])
        for item in active_memory_items:
            label = f"{item.get('memory_scope') or item.get('scope')}.{item.get('memory_type') or item.get('type')}"
            name = item.get("name") or item.get("key") or "memory"
            details = active_memory_item_detail_parts(item)
            lines.append(f"- [{label}] {name}: {item.get('description') or item.get('text') or ''} ({'; '.join(details)})")
        if active_memory.get("truncated"):
            lines.append(f"... {active_memory.get('total')} total active memories; older items omitted")

    effort = resume.get("effort") or {}
    if effort:
        steps = effort.get("steps") or {}
        lines.extend(["", "Effort budget"])
        lines.append(
            f"pressure={effort.get('pressure')} "
            f"steps={steps.get('used')}/{steps.get('budget')} remaining={steps.get('remaining')} "
            f"failures={effort.get('failures')} active_seconds={effort.get('observed_active_seconds')} "
            f"wall_seconds={effort.get('wall_elapsed_seconds')}"
        )
        warnings = effort.get("warnings") or []
        if warnings:
            lines.append(f"warnings: {', '.join(warnings)}")
        if effort.get("recommendation"):
            lines.append(f"recommendation: {effort.get('recommendation')}")

    lines.extend(["", "Recent decisions"])
    decisions = resume.get("recent_decisions") or []
    if decisions:
        seen_guidance = {}
        for decision in decisions:
            tool_text = f" tool_call=#{decision.get('tool_call_id')}" if decision.get("tool_call_id") else ""
            lines.append(
                f"#{decision.get('model_turn_id')} [{decision.get('status')}] "
                f"{decision.get('action')}{tool_text} {decision.get('summary') or ''}"
            )
            guidance = decision.get("guidance_snapshot") or decision.get("guidance")
            if guidance:
                guidance_text = _guidance_display_with_reference(
                    guidance,
                    seen_guidance,
                    decision.get("model_turn_id"),
                )
                lines.append(f"  guidance: {guidance_text}")
            plan_items = decision.get("plan_items") or []
            if plan_items:
                lines.append("  plan_items:")
                lines.extend(f"  - {item}" for item in plan_items)
            target_paths = decision.get("target_paths") or []
            if target_paths:
                lines.append(f"  target_paths: {', '.join(target_paths)}")
            last_verified_state = decision.get("last_verified_state")
            if last_verified_state:
                lines.append(f"  last_verified_state: {last_verified_state}")
            open_questions = decision.get("open_questions") or []
            if open_questions:
                lines.append("  open_questions:")
                lines.extend(f"  - {item}" for item in open_questions)
    else:
        lines.append("(none)")

    compressed_prior = resume.get("compressed_prior_think") or {}
    if compressed_prior:
        shown = compressed_prior.get("shown")
        total = compressed_prior.get("total_older_model_turns")
        lines.extend(["", f"Compressed prior think ({shown}/{total} older turn(s))"])
        for item in compressed_prior.get("items") or []:
            lines.append(
                f"#{item.get('model_turn_id')} [{item.get('status')}] "
                f"{item.get('action') or 'unknown'} {item.get('summary') or ''}".rstrip()
            )
            for key in ("hypothesis", "next_step", "last_verified_state"):
                if item.get(key):
                    lines.append(f"  {key}: {item.get(key)}")
            plan_items = item.get("plan_items") or []
            if plan_items:
                lines.append("  plan_items:")
                lines.extend(f"  - {entry}" for entry in plan_items)
            target_paths = item.get("target_paths") or []
            if target_paths:
                lines.append(f"  target_paths: {', '.join(target_paths)}")
            open_questions = item.get("open_questions") or []
            if open_questions:
                lines.append("  open_questions:")
                lines.extend(f"  - {entry}" for entry in open_questions)
            if item.get("guidance_snapshot"):
                lines.append(f"  guidance: {item.get('guidance_snapshot')}")
        if compressed_prior.get("omitted"):
            lines.append(f"... {compressed_prior.get('omitted')} older model turn(s) omitted")

    stop_request = resume.get("stop_request") or {}
    if stop_request:
        lines.extend(["", "Stop request"])
        lines.append(f"{stop_request.get('requested_at') or ''} {stop_request.get('reason') or ''}".strip())
        if stop_request.get("action"):
            lines.append(f"action: {stop_request.get('action')}")
        if stop_request.get("submit_text"):
            lines.append(f"submit: {clip_inline_text(stop_request.get('submit_text'), 500)}")

    last_stop = resume.get("last_stop_request") or {}
    if last_stop:
        lines.extend(["", "Last stop request"])
        lines.append(f"{last_stop.get('requested_at') or ''} {last_stop.get('reason') or ''}".strip())
        if last_stop.get("action"):
            lines.append(f"action: {last_stop.get('action')}")
        if last_stop.get("submit_text"):
            lines.append(f"submit: {clip_inline_text(last_stop.get('submit_text'), 500)}")

    recovery = resume.get("recovery_plan") or {}
    if recovery:
        lines.extend(["", "Recovery plan"])
        for item in recovery.get("items") or []:
            target = f"tool_call=#{item.get('tool_call_id')}" if item.get("kind") == "tool_call" else f"model_turn=#{item.get('model_turn_id')}"
            effect = f" effect={item.get('effect_classification')}" if item.get("effect_classification") else ""
            lines.append(
                f"- {target} action={item.get('action')} safety={item.get('safety')}{effect} "
                f"{item.get('reason') or ''}"
            )
            if item.get("source_summary"):
                lines.append(f"  summary: {item.get('source_summary')}")
            if item.get("source_error"):
                lines.append(f"  error: {item.get('source_error')}")
            if item.get("recovery_hint"):
                lines.append(f"  recovery_hint: {item.get('recovery_hint')}")
            if item.get("hint"):
                lines.append(f"  hint: {item.get('hint')}")
            if item.get("auto_hint"):
                lines.append(f"  auto: {item.get('auto_hint')}")
            if item.get("chat_auto_hint"):
                lines.append(f"  chat_auto: {item.get('chat_auto_hint')}")
            if item.get("path"):
                lines.append(f"  path: {item.get('path')}")
            write_world = item.get("write_world_state") or {}
            if write_world:
                lines.append(
                    f"  write_world: {write_world.get('state')} "
                    f"({write_world.get('reason') or 'no reason recorded'})"
                )
                if write_world.get("temp_paths"):
                    lines.append(f"  temp_paths: {', '.join(write_world.get('temp_paths') or [])}")
            if item.get("command"):
                lines.append(f"  command: {item.get('command')}")
            if item.get("cwd"):
                lines.append(f"  cwd: {item.get('cwd')}")
            if "exit_code" in item:
                lines.append(f"  exit: {format_exit_code(item.get('exit_code'))}")
            if item.get("review_hint"):
                lines.append(f"  review: {item.get('review_hint')}")
            for step in item.get("review_steps") or []:
                lines.append(f"  review_step: {step}")

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


def _guidance_display_with_reference(guidance, seen_guidance, owner_id):
    previous_owner = seen_guidance.get(guidance)
    if previous_owner:
        return f"same as #{previous_owner}"
    if owner_id:
        seen_guidance[guidance] = owner_id
    return guidance


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
        truncated_tools = action.get("truncated_tools")
        tools_line = f"tools: {len(tools)}"
        if isinstance(truncated_tools, int) and truncated_tools > 0:
            tools_line += f" (+{truncated_tools} truncated)"
        lines.append(tools_line)
        for index, tool in enumerate(tools[:5], start=1):
            tool_type = tool.get("type") or tool.get("tool") or "unknown"
            details = []
            for key in (
                "path",
                "query",
                "pattern",
                "command",
                "cwd",
                "base",
                "offset",
                "limit",
                "line_start",
                "line_count",
                "max_chars",
            ):
                value = tool.get(key)
                if value is not None and value != "":
                    details.append(f"{key}={clip_output(str(value), 120)}")
            suffix = " " + " ".join(details) if details else ""
            lines.append(f"- {index}. {tool_type}{suffix}")
            preview = format_work_batch_write_preview(tool)
            if preview:
                lines.extend(f"  {line}" for line in preview.splitlines())
        return "\n".join(lines)
    for key in WORK_ACTION_DISPLAY_FIELDS:
        value = _display_value(action, parameters, key)
        if value is None or value == "":
            continue
        if isinstance(value, bool) and not value and key != "apply":
            continue
        lines.append(f"{key}: {clip_output(str(value), 500)}")
    preview = format_work_batch_write_preview(action)
    if preview:
        lines.extend(preview.splitlines())
    else:
        for key in ("content", "old", "new"):
            value = _display_value(action, parameters, key)
            if value is not None:
                lines.append(f"{key}: {len(str(value))} chars")
    edits = _display_value(action, parameters, "edits")
    if isinstance(edits, list):
        lines.append(f"edits: {len(edits)} hunk(s)")
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
    tool_call.pop("running_output", None)
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


def build_work_session_timeline(session, limit=20):
    events = []
    if not session:
        return []

    def timeline_summary(text):
        return clip_inline_text(text, 240)

    order = 0
    for turn in session.get("model_turns") or []:
        order += 1
        action = turn.get("action") or {}
        action_type = action.get("type") or action.get("tool") or "unknown"
        tool_call_id = turn.get("tool_call_id")
        tool_call_ids = turn.get("tool_call_ids") or []
        if tool_call_ids:
            linked = " tool_calls=" + ",".join(f"#{value}" for value in tool_call_ids)
        else:
            linked = f" tool_call=#{tool_call_id}" if tool_call_id else ""
        events.append(
            {
                "kind": "model_turn",
                "id": turn.get("id"),
                "status": turn.get("status") or "unknown",
                "label": action_type,
                "summary": timeline_summary(turn.get("finished_note") or turn.get("summary") or turn.get("error") or ""),
                "guidance_snapshot": timeline_summary(work_turn_guidance_snapshot(turn)),
                "started_at": turn.get("started_at") or "",
                "finished_at": turn.get("finished_at") or "",
                "linked": linked,
                "order": order,
            }
        )
    for call in session.get("tool_calls") or []:
        order += 1
        summary = compact_work_tool_summary(call)
        if not summary:
            summary = summarize_work_tool_result(call.get("tool"), call.get("result") or {})
        events.append(
            {
                "kind": "tool_call",
                "id": call.get("id"),
                "status": call.get("status") or "unknown",
                "label": call.get("tool") or "unknown",
                "summary": timeline_summary(summary),
                "started_at": call.get("started_at") or "",
                "finished_at": call.get("finished_at") or "",
                "linked": "",
                "order": order,
            }
        )
    events.sort(key=lambda event: (event.get("started_at") or "", event.get("order") or 0))
    count = 20 if limit is None else max(0, int(limit))
    if count == 0:
        return []
    return events[-count:]


def format_work_session_timeline(session, task=None, limit=20):
    if not session:
        return "No active work session."
    lines = [
        f"Work timeline #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        "",
        "Events",
    ]
    events = build_work_session_timeline(session, limit=limit)
    if not events:
        lines.append("(none)")
        return "\n".join(lines)
    for event in events:
        prefix = "model" if event.get("kind") == "model_turn" else "tool"
        linked = event.get("linked") or ""
        summary = f" {event.get('summary')}" if event.get("summary") else ""
        guidance_snapshot = event.get("guidance_snapshot") or event.get("guidance")
        guidance = f" guidance={guidance_snapshot}" if guidance_snapshot else ""
        lines.append(
            f"- {event.get('started_at') or ''} {prefix}#{event.get('id')} "
            f"[{event.get('status')}] {event.get('label')}{linked}{guidance}{summary}".strip()
        )
    return "\n".join(lines)


def build_work_session_diff_entries(session, limit=8, max_chars=DEFAULT_DIFF_PREVIEW_MAX_CHARS):
    entries = []
    for call in (session or {}).get("tool_calls") or []:
        if call.get("tool") not in WRITE_WORK_TOOLS:
            continue
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        diff = result.get("diff") or ""
        if not diff:
            continue
        diff_stats = _result_diff_stats(result, diff)
        finished_at = call.get("finished_at") or ""
        entries.append(
            {
                "tool_call_id": call.get("id"),
                "status": call.get("status") or "unknown",
                "tool": call.get("tool") or "unknown",
                "path": result.get("path") or parameters.get("path") or "",
                "changed": result.get("changed"),
                "dry_run": result.get("dry_run"),
                "written": result.get("written"),
                "rolled_back": result.get("rolled_back"),
                "verification_exit_code": result.get("verification_exit_code"),
                "approval_status": call.get("approval_status") or "",
                "finished_at": finished_at,
                "recorded_at": finished_at,
                "diff_stats": diff_stats,
                "diff_preview": format_diff_preview(diff, max_chars=max_chars, diff_stats=diff_stats),
            }
        )
    return entries[-limit:]


def format_work_session_diffs(session, task=None, limit=8):
    if not session:
        return "No active work session."
    lines = [
        f"Work diffs #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        "",
        "Diffs (historical tool-call records)",
    ]
    entries = build_work_session_diff_entries(session, limit=limit)
    if not entries:
        lines.append("(none)")
        return "\n".join(lines)
    for entry in entries:
        verification = (
            f" verification_exit_code={entry.get('verification_exit_code')}"
            if entry.get("verification_exit_code") is not None
            else ""
        )
        approval = f" approval={entry.get('approval_status')}" if entry.get("approval_status") else ""
        recorded = f" recorded_at={entry.get('finished_at')}" if entry.get("finished_at") else ""
        lines.append(
            f"#{entry.get('tool_call_id')} [{entry.get('status')}] {entry.get('tool')} "
            f"{entry.get('path') or ''} changed={entry.get('changed')} "
            f"written={entry.get('written')} dry_run={entry.get('dry_run')} "
            f"rolled_back={entry.get('rolled_back')}{verification}{approval}{recorded}"
        )
        if entry.get("diff_preview"):
            lines.append(entry["diff_preview"])
    return "\n".join(lines)


def build_work_session_test_entries(session, limit=8, max_chars=1200):
    entries = []
    for call in (session or {}).get("tool_calls") or []:
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        if call.get("tool") == "run_tests" and (result.get("command") or parameters.get("command")):
            entries.append(
                {
                    "tool_call_id": call.get("id"),
                    "status": call.get("status") or "unknown",
                    "kind": "run_tests",
                    "command": result.get("command") or parameters.get("command") or "",
                    "cwd": result.get("cwd") or parameters.get("cwd") or "",
                    "exit_code": result.get("exit_code"),
                    "stdout": clip_tail(result.get("stdout") or "", max_chars),
                    "stderr": clip_tail(result.get("stderr") or "", max_chars),
                    "error": call.get("error") or "",
                    "finished_at": call.get("finished_at"),
                }
            )
        verification = result.get("verification") or {}
        if verification.get("command"):
            entries.append(
                {
                    "tool_call_id": call.get("id"),
                    "status": call.get("status") or "unknown",
                    "kind": f"{call.get('tool')}_verification",
                    "command": verification.get("command") or "",
                    "cwd": verification.get("cwd") or "",
                    "exit_code": verification.get("exit_code"),
                    "stdout": clip_tail(verification.get("stdout") or "", max_chars),
                    "stderr": clip_tail(verification.get("stderr") or "", max_chars),
                    "error": "",
                    "finished_at": verification.get("finished_at") or call.get("finished_at"),
                }
            )
    if limit is None:
        return entries
    return entries[-limit:]


def format_work_session_tests(session, task=None, limit=8):
    if not session:
        return "No active work session."
    lines = [
        f"Work tests #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        "",
        "Tests and verifications",
    ]
    entries = build_work_session_test_entries(session, limit=limit)
    if not entries:
        lines.append("(none)")
        return "\n".join(lines)
    for entry in entries:
        outcome = "passed" if entry.get("exit_code") == 0 else "failed"
        if entry.get("exit_code") is None:
            outcome = "failed" if entry.get("status") == "failed" else "unknown"
        lines.append(
            f"#{entry.get('tool_call_id')} [{outcome}] {entry.get('kind')} "
            f"exit={format_exit_code(entry.get('exit_code'))} {entry.get('command') or ''}"
        )
        if entry.get("cwd"):
            lines.append(f"cwd: {entry.get('cwd')}")
        if entry.get("stdout"):
            lines.append("stdout:")
            lines.append(entry["stdout"])
        if entry.get("stderr"):
            lines.append("stderr:")
            lines.append(entry["stderr"])
        if entry.get("error"):
            lines.append(f"error: {entry.get('error')}")
    return "\n".join(lines)


def build_work_session_command_entries(session, limit=8, max_chars=1200, include_tests=True):
    entries = []
    for call in (session or {}).get("tool_calls") or []:
        if call.get("tool") == "run_tests" and not include_tests:
            continue
        if call.get("tool") not in COMMAND_WORK_TOOLS:
            continue
        result = call.get("result") or {}
        parameters = call.get("parameters") or {}
        if result.get("command") is None and parameters.get("command") is None:
            continue
        entries.append(
            {
                "tool_call_id": call.get("id"),
                "status": call.get("status") or "unknown",
                "tool": call.get("tool") or "unknown",
                "command": result.get("command") or parameters.get("command") or "",
                "cwd": result.get("cwd") or parameters.get("cwd") or "",
                "exit_code": result.get("exit_code"),
                "stdout": clip_tail(result.get("stdout") or "", max_chars),
                "stderr": clip_tail(result.get("stderr") or "", max_chars),
                "finished_at": call.get("finished_at"),
            }
        )
    return entries[-limit:]


def format_work_session_commands(session, task=None, limit=8, include_tests=True):
    if not session:
        return "No active work session."
    lines = [
        f"Work commands #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        "",
        "Commands",
    ]
    entries = build_work_session_command_entries(session, limit=limit, include_tests=include_tests)
    if not entries:
        lines.append("(none)")
        return "\n".join(lines)
    for entry in entries:
        lines.append(
            f"#{entry.get('tool_call_id')} [{entry.get('status')}] {entry.get('tool')} "
            f"exit={format_exit_code(entry.get('exit_code'))} {entry.get('command') or ''}"
        )
        if entry.get("cwd"):
            lines.append(f"cwd: {entry.get('cwd')}")
        if entry.get("stdout"):
            lines.append("stdout:")
            lines.append(entry["stdout"])
        if entry.get("stderr"):
            lines.append("stderr:")
            lines.append(entry["stderr"])
    return "\n".join(lines)


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
    pending_steer = (resume or {}).get("pending_steer") or {}
    if pending_steer.get("text"):
        lines.append(f"pending_steer: {clip_inline_text(pending_steer.get('text'), 240)}")
    queued_followups = (resume or {}).get("queued_followups") or []
    if queued_followups:
        queued_total = int((resume or {}).get("queued_followups_total") or len(queued_followups))
        lines.append(
            f"queued_followups: {queued_total} "
            f"next={clip_inline_text(queued_followups[0].get('text'), 180)}"
        )
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
                guidance_snapshot = work_turn_guidance_snapshot(turn)
                if guidance_snapshot:
                    lines.append(f"  guidance: {clip_output(guidance_snapshot, 240)}")
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
                diff = result.get("diff") or ""
                diff_stats = _result_diff_stats(result, diff)
                approval = f" approval={call.get('approval_status')}" if call.get("approval_status") else ""
                lines.append(
                    f"#{call.get('id')} [{call.get('status')}] {call.get('tool')} "
                    f"written={result.get('written')} rolled_back={result.get('rolled_back')} "
                    f"verification_exit_code={result.get('verification_exit_code')}{approval}"
                )
                lines.append(format_diff_preview(diff, diff_stats=diff_stats))
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
