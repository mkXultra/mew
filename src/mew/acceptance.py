from __future__ import annotations

import re

from .tasks import clip_output


ACCEPTANCE_CONSTRAINT_KEYWORDS = (
    "acceptance",
    "allowed",
    "avoid",
    "compile",
    "create",
    "do not",
    "don't",
    "ensure",
    "exact",
    "expected",
    "forbid",
    "must",
    "no ",
    "not ",
    "only",
    "output",
    "pass",
    "preserve",
    "produce",
    "replace",
    "save",
    "should",
    "specified",
    "verify",
    "warning",
    "without",
)

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_TOOL_ID_RE = re.compile(r"\btool\s*#?\s*(\d+)\b", re.IGNORECASE)

_WRITE_TOOLS = {"write_file", "edit_file", "edit_file_hunks"}
_GROUNDING_TOOLS = {
    "git_diff",
    "git_status",
    "glob",
    "read_image",
    "read_file",
    "run_command",
    "run_tests",
    "search_text",
}

_EDIT_SCOPE_MARKERS = (
    "allowed edit",
    "allowed edits",
    "do not edit",
    "do not modify",
    "don't edit",
    "don't modify",
    "must not edit",
    "must not modify",
    "only edit",
    "only edits",
    "only change",
    "only changes",
    "only modify",
    "only modification",
    "only replacements",
    "replace words",
    "specified replacement",
    "specified replacements",
    "without editing",
    "without modifying",
)

_ALL_VALID_ANSWER_TASK_MARKERS = (
    "all valid",
    "all winning",
    "all possible",
    "all matching",
    "all legal",
    "multiple valid",
    "multiple winning",
    "multiple possible",
    "print them all",
    "write them all",
    "list them all",
    "one per line",
)

_COMPLETENESS_EVIDENCE_MARKERS = (
    "all legal",
    "all valid",
    "all winning",
    "all possible",
    "both",
    "candidate",
    "complete",
    "completeness",
    "enumerat",
    "exhaust",
    "found all",
    "list them all",
    "mates [",
    "multiple",
    "no other",
    "one per line",
    "winning moves",
)


def _clean_constraint_text(text: object, *, limit: int = 260) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", str(text or "").strip())
    return clip_output(cleaned, limit)


def _constraint_sentences(text: str) -> list[str]:
    normalized = _WHITESPACE_RE.sub(" ", str(text or "").strip())
    if not normalized:
        return []
    pieces = _SENTENCE_BOUNDARY_RE.split(normalized)
    if len(pieces) == 1 and len(normalized) > 320:
        pieces = re.split(r"\s*(?:;|\n|- )\s*", normalized)
    return [_clean_constraint_text(piece) for piece in pieces if _clean_constraint_text(piece)]


def extract_acceptance_constraints(text: object, *, limit: int = 8) -> list[str]:
    """Extract a compact stated-constraint checklist from task text.

    This is intentionally heuristic. The goal is not to solve a task, but to
    keep explicit acceptance and edit-scope constraints visible to the work
    loop so "local verifier passed" is not mistaken for "the task is done".
    """

    constraints: list[str] = []
    for sentence in _constraint_sentences(str(text or "")):
        lowered = sentence.casefold()
        if not any(keyword in lowered for keyword in ACCEPTANCE_CONSTRAINT_KEYWORDS):
            continue
        if sentence not in constraints:
            constraints.append(sentence)
        if len(constraints) >= limit:
            break
    return constraints


def is_edit_scope_constraint(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _EDIT_SCOPE_MARKERS)


def coerce_acceptance_checks(value: object, *, limit: int = 8) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    checks: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            check = {
                "constraint": _clean_constraint_text(item, limit=180),
                "status": "",
                "evidence": "",
            }
        elif isinstance(item, dict):
            check = {
                "constraint": _clean_constraint_text(
                    item.get("constraint") or item.get("criterion") or item.get("name"),
                    limit=180,
                ),
                "status": _clean_constraint_text(item.get("status") or item.get("result"), limit=80),
                "evidence": _clean_constraint_text(item.get("evidence") or item.get("proof"), limit=240),
            }
        else:
            continue
        if not check["constraint"] and not check["status"] and not check["evidence"]:
            continue
        checks.append(check)
        if len(checks) >= limit:
            break
    return checks


def _completed_tool_calls(session: object) -> list[dict]:
    if not isinstance(session, dict):
        return []
    calls = session.get("tool_calls")
    if not isinstance(calls, list):
        return []
    return [
        call
        for call in calls
        if isinstance(call, dict) and str(call.get("status") or "").casefold() == "completed"
    ]


def _latest_completed_write_tool_id(session: object) -> int | None:
    latest: int | None = None
    for call in _completed_tool_calls(session):
        if call.get("tool") not in _WRITE_TOOLS:
            continue
        call_id = call.get("id")
        if isinstance(call_id, int):
            latest = max(latest or call_id, call_id)
    return latest


def _tool_call_by_id(session: object, tool_id: int) -> dict | None:
    for call in _completed_tool_calls(session):
        if call.get("id") == tool_id:
            return call
    return None


def _tool_call_text(call: object) -> str:
    if not isinstance(call, dict):
        return ""
    chunks: list[str] = []
    for key in ("summary", "error"):
        value = call.get(key)
        if value:
            chunks.append(str(value))
    result = call.get("result")
    if isinstance(result, dict):
        for key in ("text", "stdout", "stderr", "summary", "output"):
            value = result.get(key)
            if value:
                chunks.append(str(value))
    elif result:
        chunks.append(str(result))
    return "\n".join(chunks)


def _evidence_tool_ids(text: object) -> list[int]:
    ids: list[int] = []
    for match in _TOOL_ID_RE.finditer(str(text or "")):
        try:
            tool_id = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if tool_id not in ids:
            ids.append(tool_id)
    return ids


def _has_post_write_grounding_evidence(evidence: object, session: object) -> bool:
    latest_write_id = _latest_completed_write_tool_id(session)
    if latest_write_id is None:
        return True
    for tool_id in _evidence_tool_ids(evidence):
        if tool_id <= latest_write_id:
            continue
        call = _tool_call_by_id(session, tool_id)
        if call and call.get("tool") in _GROUNDING_TOOLS:
            return True
    return False


def is_all_valid_answer_task(text: object) -> bool:
    lowered = str(text or "").casefold()
    if not any(marker in lowered for marker in _ALL_VALID_ANSWER_TASK_MARKERS):
        return False
    return any(marker in lowered for marker in ("all", "multiple", "one per line"))


def _has_completeness_marker(text: object) -> bool:
    lowered = str(text or "").casefold()
    return any(marker in lowered for marker in _COMPLETENESS_EVIDENCE_MARKERS)


def _has_all_valid_answer_grounding_evidence(evidence: object, session: object) -> bool:
    if not _has_completeness_marker(evidence):
        return False
    for tool_id in _evidence_tool_ids(evidence):
        call = _tool_call_by_id(session, tool_id)
        if not call or call.get("tool") not in _GROUNDING_TOOLS:
            continue
        if _has_completeness_marker(_tool_call_text(call)):
            return True
    return False


def _all_valid_answer_grounding_blocker(
    task_description: object,
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if not is_all_valid_answer_task(task_description):
        return ""
    completeness_checks = [
        check
        for check in checks
        if _has_completeness_marker(check.get("constraint"))
        or _has_completeness_marker(check.get("evidence"))
    ]
    if not completeness_checks:
        return (
            "all-valid answer completeness evidence missing: tasks asking for all, "
            "multiple, or one-per-line valid answers must cite independent enumeration "
            "or completeness proof before task_done=true"
        )
    for check in completeness_checks:
        if _has_all_valid_answer_grounding_evidence(check.get("evidence"), session):
            return ""
    return (
        "all-valid answer completeness evidence ungrounded: completeness checks must "
        "cite a completed grounding tool whose output independently enumerates or "
        "proves the full answer set"
    )


def _edit_scope_grounding_blocker(
    constraints: list[str],
    checks: list[dict[str, str]],
    session: object,
) -> str:
    if _latest_completed_write_tool_id(session) is None:
        return ""
    if not any(is_edit_scope_constraint(constraint) for constraint in constraints):
        return ""
    edit_scope_checks = [
        check
        for check in checks
        if is_edit_scope_constraint(check.get("constraint")) or is_edit_scope_constraint(check.get("evidence"))
    ]
    if not edit_scope_checks:
        return (
            "edit-scope acceptance evidence missing: constraints about only-allowed edits, "
            "specified replacements, or do-not-edit surfaces must be checked explicitly"
        )
    for check in edit_scope_checks:
        if _has_post_write_grounding_evidence(check.get("evidence"), session):
            continue
        return (
            "edit-scope acceptance evidence ungrounded: constraints about only-allowed edits, "
            "specified replacements, or do-not-edit surfaces must cite a completed validator, "
            "diff, or final inspection tool after the latest write; write history alone is not enough"
        )
    return ""


def acceptance_finish_blocker(task_description: object, action: object, *, session: object = None) -> str:
    action = action if isinstance(action, dict) else {}
    if not action.get("task_done"):
        return ""
    checks = coerce_acceptance_checks(action.get("acceptance_checks"))
    all_valid_answer_blocker = _all_valid_answer_grounding_blocker(task_description, checks, session)
    if all_valid_answer_blocker:
        return all_valid_answer_blocker
    constraints = extract_acceptance_constraints(task_description)
    if not constraints:
        return ""
    verified = [
        check
        for check in checks
        if check.get("constraint")
        and check.get("evidence")
        and str(check.get("status") or "").casefold() in {"pass", "passed", "satisfied", "verified", "ok"}
    ]
    if len(verified) >= len(constraints):
        edit_scope_blocker = _edit_scope_grounding_blocker(constraints, verified, session)
        if edit_scope_blocker:
            return edit_scope_blocker
        return ""
    return (
        "acceptance constraints unchecked: finish with task_done=true must include "
        "acceptance_checks with verified status and direct evidence for every stated constraint"
    )
