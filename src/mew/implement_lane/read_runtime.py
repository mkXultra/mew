"""Read-only tool execution for the default-off implement_v2 lane."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

from ..read_tools import (
    glob_paths,
    inspect_dir,
    is_sensitive_path,
    read_file,
    resolve_allowed_path,
    search_text,
    summarize_read_result,
)
from ..tasks import clip_output
from ..timeutil import now_iso
from .replay import build_invalid_tool_result
from .types import ToolCallEnvelope, ToolResultEnvelope

READ_ONLY_TOOL_NAMES = frozenset({"inspect_dir", "read_file", "search_text", "glob", "git_status", "git_diff"})
WRITE_OR_EXECUTE_TOOL_NAMES = frozenset(
    {"run_command", "run_tests", "poll_command", "cancel_command", "write_file", "edit_file", "apply_patch"}
)
DEFAULT_V2_READ_RESULT_MAX_CHARS = 12_000


def execute_read_only_tool_call(
    call: ToolCallEnvelope,
    *,
    workspace: object,
    allowed_roots: tuple[str, ...] | list[str] | None = None,
    result_max_chars: int = DEFAULT_V2_READ_RESULT_MAX_CHARS,
) -> ToolResultEnvelope:
    """Execute one provider-native read-only call and return its paired result."""

    roots = _allowed_roots(workspace=workspace, allowed_roots=allowed_roots)
    if call.tool_name in WRITE_OR_EXECUTE_TOOL_NAMES:
        return _error_result(call, status="denied", reason=f"tool is not available in read-only mode: {call.tool_name}")
    if call.tool_name not in READ_ONLY_TOOL_NAMES:
        return build_invalid_tool_result(call, reason=f"unknown read-only tool: {call.tool_name}")
    try:
        payload = _execute_read_only_payload(call, workspace=workspace, allowed_roots=roots)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return _error_result(call, status="failed", reason=str(exc))

    clipped_payload, clipped = _clip_payload(payload, max_chars=result_max_chars)
    content_refs = _content_refs_for_payload(call, payload=payload, clipped=clipped)
    if _git_payload_failed(call, payload):
        return ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="failed",
            is_error=True,
            content=(_payload_with_reason(clipped_payload),),
            content_refs=content_refs,
        )
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        is_error=False,
        content=(clipped_payload,),
        content_refs=content_refs,
        evidence_refs=_evidence_refs_for_payload(call, payload=payload),
    )


def extract_inspected_paths(results: tuple[ToolResultEnvelope, ...] | list[ToolResultEnvelope]) -> tuple[str, ...]:
    """Return stable inspected path values from completed read-only results."""

    paths: list[str] = []
    seen: set[str] = set()
    for result in results:
        if result.status != "completed" or result.is_error:
            continue
        for item in result.content:
            if isinstance(item, dict):
                for path in _payload_paths(item):
                    if path not in seen:
                        paths.append(path)
                        seen.add(path)
    return tuple(paths)


def _execute_read_only_payload(
    call: ToolCallEnvelope,
    *,
    workspace: object,
    allowed_roots: tuple[str, ...],
) -> dict[str, object]:
    args = dict(call.arguments)
    tool = call.tool_name
    if tool == "inspect_dir":
        payload = inspect_dir(
            _workspace_path(args.get("path") or ".", workspace),
            allowed_roots,
            limit=_bounded_int(args.get("limit"), 50, 1, 200),
        )
        payload["summary"] = summarize_read_result("inspect_dir", payload)
        return payload
    if tool == "read_file":
        payload = read_file(
            _workspace_path(args.get("path") or "", workspace),
            allowed_roots,
            max_chars=_bounded_int(args.get("max_chars"), 8_000, 1, 50_000),
            offset=_bounded_int(args.get("offset"), 0, 0, 1_000_000),
            line_start=args.get("line_start"),
            line_count=args.get("line_count"),
        )
        payload["summary"] = summarize_read_result("read_file", payload)
        return payload
    if tool == "search_text":
        query = args.get("query")
        include_pattern = args.get("pattern")
        regex = bool(args.get("regex"))
        if (query is None or not str(query).strip()) and include_pattern is not None:
            # Some provider turns use ``pattern`` as the search term because the
            # prompt surface names glob and search arguments similarly. Treat a
            # lone pattern as the query instead of spending a recovery turn. If
            # it looks like a content regex (for example ``foo|bar``), preserve
            # that intent instead of running a fixed-string search for the
            # whole expression.
            query = include_pattern
            include_pattern = None
            regex = regex or _search_query_looks_regex(query)
        payload = search_text(
            query or "",
            _workspace_path(args.get("path") or ".", workspace),
            allowed_roots,
            max_matches=_bounded_int(args.get("max_matches"), 50, 1, 200),
            context_lines=_bounded_int(args.get("context_lines"), 3, 0, 5),
            pattern=include_pattern,
            regex=regex,
        )
        payload["summary"] = summarize_read_result("search_text", payload)
        return payload
    if tool == "glob":
        pattern = args.get("pattern") or ""
        path = args.get("path") or "."
        if (pattern is None or not str(pattern).strip()) and _looks_like_glob_path(path):
            path, pattern = _split_glob_path_argument(path, workspace=workspace)
        payload = glob_paths(
            pattern,
            _workspace_path(path or ".", workspace),
            allowed_roots,
            max_matches=_bounded_int(args.get("max_matches"), 100, 1, 500),
        )
        payload["summary"] = summarize_read_result("glob", payload)
        return payload
    if tool == "git_status":
        cwd = _resolve_allowed_git_cwd(_workspace_path(args.get("cwd") or ".", workspace), allowed_roots)
        return _run_safe_git_status(cwd, allowed_roots=allowed_roots)
    if tool == "git_diff":
        cwd = _resolve_allowed_git_cwd(_workspace_path(args.get("cwd") or ".", workspace), allowed_roots)
        return _run_safe_git_diff(
            cwd,
            allowed_roots=allowed_roots,
            staged=bool(args.get("staged")),
            base=str(args.get("base") or ""),
        )
    raise ValueError(f"unknown read-only tool: {tool}")


def _workspace_path(path: object, workspace: object) -> str:
    requested = Path(str(path or ".")).expanduser()
    if requested.is_absolute():
        return str(requested)
    return str((Path(str(workspace or ".")).expanduser() / requested).resolve(strict=False))


def _looks_like_glob_path(path: object) -> bool:
    text = str(path or "")
    return any(marker in text for marker in ("*", "?", "["))


def _split_glob_path_argument(path: object, *, workspace: object) -> tuple[str, str]:
    """Accept provider calls that put the glob expression in ``path``.

    The model-facing surface describes ``glob`` as workspace path discovery, and
    provider turns sometimes send ``{"path": "/workspace/**/*"}`` instead of a
    separate ``pattern``.  Keep the actual read tool strict by translating that
    shape to ``path=/workspace`` plus a relative pattern.
    """

    raw = str(path or ".").strip() or "."
    requested = Path(raw).expanduser()
    parts = requested.parts
    glob_index = next(
        (
            index
            for index, part in enumerate(parts)
            if any(marker in part for marker in ("*", "?", "["))
        ),
        None,
    )
    if glob_index is None:
        return raw, ""
    base_parts = parts[:glob_index]
    pattern_parts = parts[glob_index:]
    if not base_parts:
        base = "."
    elif base_parts == (requested.anchor,):
        base = requested.anchor
    else:
        base = str(Path(*base_parts))
    pattern = str(Path(*pattern_parts)) if pattern_parts else "*"
    if requested.is_absolute():
        workspace_path = Path(str(workspace or ".")).expanduser().resolve(strict=False)
        try:
            base_path = Path(base).expanduser().resolve(strict=False)
            if base_path == workspace_path or base_path.is_relative_to(workspace_path):
                base = str(base_path)
        except OSError:
            pass
    return base, pattern


def _allowed_roots(*, workspace: object, allowed_roots: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    values = [str(root) for root in allowed_roots or () if str(root or "").strip()]
    if not values:
        values = [str(workspace or ".")]
    return tuple(values)


def _resolve_allowed_git_cwd(cwd: object, allowed_roots: tuple[str, ...]) -> Path:
    resolved = resolve_allowed_path(cwd or ".", allowed_roots)
    if resolved.is_file():
        resolved = resolved.parent
    if not resolved.is_dir():
        raise ValueError(f"git cwd is not a directory: {resolved}")
    _validated_git_top_level(resolved, allowed_roots=allowed_roots)
    return resolved


def _validated_git_top_level(cwd: Path, *, allowed_roots: tuple[str, ...]) -> Path:
    result = _run_git_probe(cwd, ("rev-parse", "--show-toplevel"))
    if result.returncode != 0:
        raise ValueError("git cwd is not inside a git repository")
    top_level = Path((result.stdout or "").strip()).expanduser().resolve(strict=True)
    allowed = tuple(Path(root).expanduser().resolve(strict=True) for root in allowed_roots)
    if not any(top_level == root or _is_relative_to(top_level, root) for root in allowed):
        allowed_text = ", ".join(str(root) for root in allowed)
        raise ValueError(f"git repository root is outside allowed read roots: {top_level}; allowed={allowed_text}")
    return top_level


def _run_safe_git_status(cwd: Path, *, allowed_roots: tuple[str, ...]) -> dict[str, object]:
    _validated_git_top_level(cwd, allowed_roots=allowed_roots)
    return _run_safe_git_record(cwd, ("status", "--short", "--untracked-files=all", "--", "."))


def _run_safe_git_diff(cwd: Path, *, allowed_roots: tuple[str, ...], staged: bool, base: str) -> dict[str, object]:
    _validated_git_top_level(cwd, allowed_roots=allowed_roots)
    base = _validate_git_ref(base)
    if staged and base:
        raise ValueError("--staged and --base cannot be combined")
    args = ["diff", "--no-ext-diff", "--no-textconv"]
    if base:
        args.append(f"{base}...HEAD")
    elif staged:
        args.append("--staged")
    args.extend(["--stat", "--", "."])
    record = _run_safe_git_record(cwd, tuple(args))
    record["stat_forced"] = True
    return record


def _run_safe_git_record(cwd: Path, args: tuple[str, ...]) -> dict[str, object]:
    started_at = now_iso()
    command = ("git", *_safe_git_global_args(), *args)
    result = _run_git_probe(cwd, args)
    return {
        "command": " ".join(command),
        "argv": list(command),
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": now_iso(),
        "exit_code": result.returncode,
        "stdout": clip_output(_filter_sensitive_git_stdout(result.stdout), 12_000),
        "stderr": clip_output(result.stderr, 4_000),
    }


def _run_git_probe(cwd: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    command = ("git", *_safe_git_global_args(), *args)
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=15,
        shell=False,
        env=_safe_git_env(cwd),
    )


def _safe_git_global_args() -> tuple[str, ...]:
    return (
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.pager=cat",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "diff.external=",
    )


def _safe_git_env(cwd: Path) -> dict[str, str]:
    env = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "HOME": str(cwd),
        "LC_ALL": os.environ.get("LC_ALL") or "C.UTF-8",
        "PATH": os.environ.get("PATH") or "/usr/bin:/bin",
        "PAGER": "cat",
    }
    return env


def _validate_git_ref(ref: object) -> str:
    text = str(ref or "").strip()
    if not text:
        return ""
    if text.startswith("-") or any(char.isspace() for char in text):
        raise ValueError("git ref must not start with '-' or contain whitespace")
    return text


def _filter_sensitive_git_stdout(stdout: str) -> str:
    lines = []
    for line in (stdout or "").splitlines():
        if _git_line_has_sensitive_path(line):
            lines.append("[sensitive path redacted]")
        else:
            lines.append(line)
    return "\n".join(lines)


def _git_line_has_sensitive_path(line: str) -> bool:
    return any(is_sensitive_path(candidate) for candidate in _git_line_path_candidates(line))


def _git_line_path_candidates(line: str) -> tuple[str, ...]:
    text = str(line or "")
    if "|" in text:
        text = text.split("|", 1)[0].strip()
    elif len(text) > 3 and text[:2].strip():
        text = text[3:].strip()
    candidates = []
    for part in (text, *re.split(r"\s+(?:->|=>)\s+", text)):
        cleaned = part.strip().strip("{}")
        if cleaned:
            candidates.append(cleaned)
    return tuple(candidates)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _search_query_looks_regex(value: object) -> bool:
    text = str(value or "")
    if not text:
        return False
    return any(token in text for token in ("|", ".*", "\\b", "[", "]", "(", ")", "+", "?"))


def _error_result(call: ToolCallEnvelope, *, status: str, reason: str) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status=status,
        is_error=True,
        content=({"reason": reason},),
    )


def _clip_payload(payload: dict[str, object], *, max_chars: int) -> tuple[dict[str, object], bool]:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    if len(text) <= max_chars:
        return dict(payload), False
    clipped = dict(payload)
    clipped["mew_content_truncated"] = True
    for key in ("text", "stdout", "stderr", "summary"):
        value = clipped.get(key)
        if isinstance(value, str) and len(value) > 1_000:
            clipped[key] = f"{value[:1000]}\n... content truncated ..."
    text = json.dumps(clipped, ensure_ascii=True, sort_keys=True)
    if len(text) > max_chars:
        clipped = {
            "mew_content_truncated": True,
            "path": payload.get("path"),
            "type": payload.get("type") or "read_result",
            "summary": str(payload.get("summary") or "")[: min(1_000, max_chars)],
            "truncated": True,
        }
    return clipped, True


def _content_refs_for_payload(
    call: ToolCallEnvelope,
    *,
    payload: dict[str, object],
    clipped: bool,
) -> tuple[str, ...]:
    if not clipped and not payload.get("truncated"):
        return ()
    return (f"implement-v2-read://{call.lane_attempt_id}/{call.provider_call_id}/content",)


def _git_payload_failed(call: ToolCallEnvelope, payload: dict[str, object]) -> bool:
    if call.tool_name not in {"git_status", "git_diff"}:
        return False
    return payload.get("exit_code") != 0


def _payload_with_reason(payload: dict[str, object]) -> dict[str, object]:
    failed = dict(payload)
    failed["reason"] = failed.get("stderr") or failed.get("stdout") or "git command failed"
    return failed


def _evidence_refs_for_payload(call: ToolCallEnvelope, *, payload: dict[str, object]) -> tuple[str, ...]:
    if payload.get("path") or payload.get("cwd"):
        return (f"implement-v2-read://{call.lane_attempt_id}/{call.provider_call_id}/evidence",)
    return ()


def _payload_paths(payload: dict[str, object]) -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("path", "cwd"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    for match in payload.get("matches") or ():
        if isinstance(match, dict):
            value = match.get("path")
            if isinstance(value, str) and value:
                paths.append(value)
    return tuple(paths)


__all__ = [
    "DEFAULT_V2_READ_RESULT_MAX_CHARS",
    "READ_ONLY_TOOL_NAMES",
    "execute_read_only_tool_call",
    "extract_inspected_paths",
]
