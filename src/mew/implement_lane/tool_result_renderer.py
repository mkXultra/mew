"""Profile-aware provider-visible tool-result rendering for implement_v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .affordance_visibility import (
    CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS,
    fields_from_forbidden_violations,
    scan_forbidden_provider_visible,
)
from .tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID
from .types import ToolResultEnvelope

RENDERER_SCHEMA_VERSION = 1
MEW_LEGACY_RENDERER_ID = "mew_legacy_result_cards_v1"
CODEX_TERMINAL_RENDERER_ID = "codex_terminal_text_v2"
CODEX_APPLY_PATCH_RENDERER_ID = "codex_apply_patch_text_v1"
CODEX_FINISH_RENDERER_ID = "codex_finish_text_v1"
CODEX_GENERIC_RENDERER_ID = "codex_generic_text_v1"
DEFAULT_RENDER_LIMIT = 12_000

_COMMAND_TOOL_NAMES = frozenset(
    {
        "exec_command",
        "write_stdin",
        "run_command",
        "run_tests",
        "poll_command",
        "cancel_command",
        "read_command_output",
    }
)
_NONTERMINAL_STATUSES = frozenset({"running", "yielded"})


@dataclass(frozen=True)
class RenderedToolResult:
    """Provider-visible rendering plus internal observability metadata."""

    text: str
    profile_id: str
    renderer_id: str
    output_bytes: int
    output_chars: int
    leak_ok: bool
    leak_fields: tuple[str, ...]

    def metrics_ref(self, *, lane_attempt_id: str, call_id: str) -> str:
        safe_lane = _safe_ref_part(lane_attempt_id)
        safe_call = _safe_ref_part(call_id)
        safe_profile = _safe_ref_part(self.profile_id)
        return f"tool-render://{safe_lane}/{safe_call}/{safe_profile}/{self.renderer_id}"

    def as_metrics(self, *, tool_name: str, call_id: str = "") -> dict[str, object]:
        return {
            "schema_version": RENDERER_SCHEMA_VERSION,
            "profile_id": self.profile_id,
            "renderer_id": self.renderer_id,
            "tool_name": tool_name,
            "call_id": call_id,
            "output_bytes": self.output_bytes,
            "output_chars": self.output_chars,
            "leak_ok": self.leak_ok,
            "leak_fields": list(self.leak_fields),
        }


def render_tool_result_for_profile(
    result: ToolResultEnvelope,
    *,
    profile_id: str,
    limit: int = DEFAULT_RENDER_LIMIT,
) -> RenderedToolResult:
    """Render a tool result according to the selected provider-visible profile."""

    if profile_id != CODEX_HOT_PATH_PROFILE_ID:
        text = result.natural_result_text()
        return _rendered(
            text,
            profile_id=profile_id or MEW_LEGACY_PROFILE_ID,
            renderer_id=MEW_LEGACY_RENDERER_ID,
            tool_name=result.tool_name,
        )
    if _is_command_family(result):
        text = _render_codex_terminal(result, limit=limit)
        return _rendered(
            text,
            profile_id=profile_id,
            renderer_id=CODEX_TERMINAL_RENDERER_ID,
            tool_name=result.tool_name,
        )
    if result.tool_name == "apply_patch":
        text = _render_codex_apply_patch(result, limit=limit)
        return _rendered(
            text,
            profile_id=profile_id,
            renderer_id=CODEX_APPLY_PATCH_RENDERER_ID,
            tool_name=result.tool_name,
        )
    if result.tool_name == "finish":
        text = _render_codex_finish(result, limit=limit)
        return _rendered(
            text,
            profile_id=profile_id,
            renderer_id=CODEX_FINISH_RENDERER_ID,
            tool_name=result.tool_name,
        )
    text = _render_codex_generic(result, limit=limit)
    return _rendered(
        text,
        profile_id=profile_id,
        renderer_id=CODEX_GENERIC_RENDERER_ID,
        tool_name=result.tool_name,
    )


def render_observability_record(
    *,
    metrics_ref: str,
    tool_name: str,
    call_id: str,
    output_text: str,
) -> dict[str, object]:
    """Build a derived sidecar row for rendered provider-visible output."""

    renderer_id = _renderer_id_from_metrics_ref(metrics_ref)
    profile_id = _profile_id_from_metrics_ref(metrics_ref)
    violations = scan_forbidden_provider_visible(output_text, surface="rendered_tool_output")
    return {
        "schema_version": RENDERER_SCHEMA_VERSION,
        "metrics_ref": metrics_ref,
        "profile_id": profile_id,
        "renderer_id": renderer_id,
        "tool_name": tool_name,
        "call_id": call_id,
        "output_bytes": len(output_text.encode("utf-8")),
        "output_chars": len(output_text),
        "leak_ok": not violations,
        "leak_fields": fields_from_forbidden_violations(violations),
        "provider_visible_debug_omissions": _provider_visible_debug_omissions(renderer_id),
    }


def _rendered(
    text: str,
    *,
    profile_id: str,
    renderer_id: str,
    tool_name: str,
) -> RenderedToolResult:
    text = str(text or "")
    violations = scan_forbidden_provider_visible(text, surface=f"rendered_tool_output:{tool_name}")
    return RenderedToolResult(
        text=text,
        profile_id=profile_id,
        renderer_id=renderer_id,
        output_bytes=len(text.encode("utf-8")),
        output_chars=len(text),
        leak_ok=not violations,
        leak_fields=tuple(fields_from_forbidden_violations(violations)),
    )


def _render_codex_terminal(result: ToolResultEnvelope, *, limit: int) -> str:
    payload = _payload(result)
    command_run_id = str(payload.get("command_run_id") or "").strip()
    if _terminal_status(result, payload) in _NONTERMINAL_STATUSES:
        session_id = command_run_id or str(payload.get("session_id") or result.provider_call_id or "unknown")
        return _clip(f"Process running with session ID {session_id}", limit)

    output = _command_output_text(result, payload, limit=limit)
    exit_code = _exit_code(result, payload)
    if result.is_error or result.status in {"failed", "invalid", "interrupted"} or exit_code not in {"0", ""}:
        lines = [f"exit_code: {exit_code}"]
        if output:
            lines.append(output)
        return _clip("\n".join(lines).rstrip(), limit)
    return _clip(output, limit)


def _render_codex_apply_patch(result: ToolResultEnvelope, *, limit: int) -> str:
    payload = _payload(result)
    if result.is_error or result.status not in {"completed"}:
        reason = _safe_apply_patch_failure_reason(_first_text(payload, "reason", "message", "error", "summary") or result.status)
        lines = [f"apply_patch failed: {reason}"]
        lines.extend(_apply_patch_failure_context_lines(payload))
        return _clip("\n".join(lines), limit)
    paths = _changed_paths(payload)
    if not paths:
        path = str(payload.get("path") or "").strip()
        if path:
            paths = (path,)
    lines = ["Success. Updated files:"]
    if paths:
        operation = _patch_op_prefix(payload)
        lines.extend(f"{operation} {path}" for path in paths[:12])
    else:
        lines.append("M <unknown>")
    diffstat = _compact_diffstat(payload)
    if diffstat:
        lines.append(diffstat)
    return _clip("\n".join(lines), limit)


def _safe_apply_patch_failure_reason(reason: str) -> str:
    marker = "unsupported apply_patch hunk line:"
    if marker not in reason:
        return reason
    prefix, _marker, _raw_line = reason.partition(marker)
    return f"{prefix}{marker.removesuffix(':')}".strip()


def _apply_patch_failure_context_lines(payload: Mapping[str, object]) -> list[str]:
    lines: list[str] = []
    for item in _apply_patch_anchor_items(payload)[:2]:
        path = _first_text(item, "path") or _first_text(payload, "path")
        if not path:
            paths = payload.get("paths")
            if isinstance(paths, list) and paths:
                path = str(paths[0])
        label = "current match"
        windows = item.get("matching_existing_windows")
        if not isinstance(windows, list) or not windows:
            windows = item.get("nearest_existing_windows")
            label = "nearest current context"
        if not isinstance(windows, list):
            continue
        for window in [window for window in windows if isinstance(window, dict)][:2]:
            location = _format_patch_window_location(path, window)
            if location:
                lines.append(f"{label}: {location}")
            snippet = _first_text(window, "text")
            if snippet:
                lines.append(_clip(snippet, 700))
    return lines


def _apply_patch_anchor_items(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    windows = payload.get("patch_anchor_windows")
    if not isinstance(windows, list):
        return []
    return [item for item in windows if isinstance(item, Mapping)]


def _format_patch_window_location(path: str, window: Mapping[str, object]) -> str:
    line_start = window.get("line_start")
    line_end = window.get("line_end")
    if isinstance(line_start, int) and isinstance(line_end, int):
        return f"{path}:{line_start}-{line_end}" if path else f"line {line_start}-{line_end}"
    if path:
        return path
    return ""


def _render_codex_finish(result: ToolResultEnvelope, *, limit: int) -> str:
    payload = _payload(result)
    summary = _first_text(payload, "summary", "reason", "outcome") or result.status
    if result.is_error or result.status not in {"completed"}:
        return _clip(f"finish blocked: {summary}", limit)
    return _clip(f"finish accepted: {summary}", limit)


def _render_codex_generic(result: ToolResultEnvelope, *, limit: int) -> str:
    payload = _payload(result)
    summary = _first_text(payload, "summary", "reason", "message", "error")
    if summary:
        return _clip(f"{result.tool_name} result: {result.status}\n{summary}", limit)
    return _clip(result.natural_result_text(limit=limit), limit)


def _is_command_family(result: ToolResultEnvelope) -> bool:
    if result.tool_name in _COMMAND_TOOL_NAMES:
        return True
    payload = _payload(result)
    return str(payload.get("internal_kernel") or "") in _COMMAND_TOOL_NAMES


def _payload(result: ToolResultEnvelope) -> dict[str, object]:
    return dict(result.content[0]) if result.content and isinstance(result.content[0], Mapping) else {}


def _terminal_status(result: ToolResultEnvelope, payload: Mapping[str, object]) -> str:
    return str(payload.get("status") or result.status or "").strip().casefold()


def _exit_code(result: ToolResultEnvelope, payload: Mapping[str, object]) -> str:
    raw = payload.get("exit_code")
    if raw not in (None, ""):
        return str(raw)
    return "1" if result.is_error or result.status in {"failed", "invalid", "interrupted"} else "0"


def _command_output_text(result: ToolResultEnvelope, payload: Mapping[str, object], *, limit: int) -> str:
    failed = result.is_error or result.status in {"failed", "invalid", "interrupted"} or _exit_code(result, payload) not in {"0", ""}
    ordered_keys = (
        ("stderr_tail", "stderr", "stdout_tail", "stdout", "reason", "message", "error", "summary")
        if failed
        else ("stdout_tail", "stdout", "stderr_tail", "stderr", "summary", "reason", "message", "error")
    )
    chunks: list[str] = []
    for key in ordered_keys:
        value = payload.get(key)
        text = str(value or "").strip() if value not in (None, "", [], {}) else ""
        if not text:
            continue
        label = key.removesuffix("_tail")
        if label in {"stdout", "stderr"} and any(part.startswith(f"{label}:") for part in chunks):
            continue
        if label in {"stdout", "stderr"}:
            full_stream = str(payload.get(label) or "").strip()
            tail_stream = str(payload.get(f"{label}_tail") or "").strip()
            stream_text = _head_tail_output_text(
                full_stream or text,
                tail_stream if full_stream else "",
                limit=max(200, limit - len(label) - 2),
            )
            chunks.append(f"{label}:\n{stream_text}")
        else:
            chunks.append(_sanitize_visible_text(text))
        if len("\n".join(chunks)) >= limit:
            break
    if not chunks:
        chunks.append(str(payload.get("status") or result.status or ""))
    return _clip("\n\n".join(chunks).strip(), limit)


def _head_tail_output_text(text: str, tail: str = "", *, limit: int) -> str:
    """Preserve both early and final terminal facts in a bounded transcript."""

    text = _sanitize_visible_text(str(text or "").strip())
    tail = _sanitize_visible_text(str(tail or "").strip())
    limit = max(0, int(limit))
    if not text:
        return _clip(tail, limit)
    if len(text) <= limit and (not tail or tail in text):
        return text
    if tail and tail not in text:
        separator = "\n...\ntail:\n"
        if len(text) + len(separator) + len(tail) <= limit:
            return f"{text.rstrip()}{separator}{tail.lstrip()}"
    marker_template = "\n...[output clipped {omitted} chars]...\n"
    if limit <= len(marker_template.format(omitted=len(text))):
        return _clip(text, limit)
    total_display_chars = len(text) + (0 if not tail or tail in text else len(tail))
    omitted = total_display_chars
    head_len = 0
    tail_len = 0
    for _ in range(3):
        marker = marker_template.format(omitted=omitted)
        body_budget = max(0, limit - len(marker))
        if tail:
            tail_len = min(len(tail), max(1, body_budget // 2))
            head_len = max(1, min(len(text), body_budget - tail_len))
        else:
            head_len = max(1, min(len(text), body_budget * 2 // 3))
            tail_len = max(0, min(len(text) - head_len, body_budget - head_len))
        omitted = max(0, total_display_chars - head_len - tail_len)
    marker = marker_template.format(omitted=omitted)
    tail_text = tail[-tail_len:] if tail else text[-tail_len:] if tail_len else ""
    return f"{text[:head_len].rstrip()}{marker}{tail_text.lstrip()}"


def _content_ref_footer(
    result: ToolResultEnvelope,
    payload: Mapping[str, object],
    *,
    visible_output: str,
) -> str:
    ref = next((str(item).strip() for item in result.content_refs if str(item).strip()), "")
    if not ref:
        return ""
    output_bytes = _int(payload.get("output_bytes"), default=-1)
    visible_limit = _int(payload.get("provider_visible_output_chars"), default=DEFAULT_RENDER_LIMIT)
    needs_ref = (
        bool(payload.get("output_truncated"))
        or not visible_output.strip()
        or (output_bytes >= 0 and output_bytes > visible_limit)
    )
    return f"Refs: output={ref}" if needs_ref else ""


def _tool_result_ref_footer(result: ToolResultEnvelope) -> str:
    """Expose the compact alias for this result without declaring it sufficient."""

    if result.status != "completed" or result.is_error or not result.evidence_refs:
        return ""
    call_id = str(result.provider_call_id or "").strip()
    if not call_id:
        return ""
    return f"Tool result ref: ev:tool_result:{call_id}"


def _changed_paths(payload: Mapping[str, object]) -> tuple[str, ...]:
    raw = payload.get("changed_paths")
    if isinstance(raw, (list, tuple)):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    return ()


def _patch_op_prefix(payload: Mapping[str, object]) -> str:
    op = str(payload.get("patch_operation") or payload.get("operation") or "").strip().casefold()
    if "add" in op:
        return "A"
    if "delete" in op or "remove" in op:
        return "D"
    if "rename" in op or "move" in op:
        return "R"
    return "M"


def _compact_diffstat(payload: Mapping[str, object]) -> str:
    stats = payload.get("diff_stats")
    if not isinstance(stats, Mapping):
        stats = payload.get("typed_source_mutation")
        if isinstance(stats, Mapping):
            stats = stats.get("diff_stats")
    if not isinstance(stats, Mapping):
        return ""
    added = stats.get("added")
    removed = stats.get("removed")
    if added is None or removed is None:
        return ""
    text = f"Diffstat: +{added}/-{removed}"
    return text if len(text) <= 80 else ""


def _first_text(payload: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return _sanitize_visible_text(" ".join(str(value).split()))
    return ""


def _sanitize_visible_text(text: str) -> str:
    cleaned = str(text or "")
    for field_name in sorted(CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS, key=len, reverse=True):
        cleaned = cleaned.replace(field_name, "[redacted]")
    return cleaned


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    limit = max(0, int(limit))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_ref_part(value: str) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in "._:-" else "-" for ch in text) or "unknown"


def _renderer_id_from_metrics_ref(metrics_ref: str) -> str:
    parts = str(metrics_ref or "").rstrip("/").rsplit("/", 1)
    return parts[-1] if len(parts) == 2 else ""


def _profile_id_from_metrics_ref(metrics_ref: str) -> str:
    parts = str(metrics_ref or "").rstrip("/").split("/")
    if len(parts) >= 2:
        profile = parts[-2]
        if profile:
            return profile
    return MEW_LEGACY_PROFILE_ID


def _provider_visible_debug_omissions(renderer_id: str) -> list[str]:
    """Describe fields intentionally kept in sidecars instead of model-visible text."""

    if renderer_id == CODEX_TERMINAL_RENDERER_ID:
        return [
            "chunk_id",
            "duration_seconds",
            "token_count",
            "tool_result_ref",
            "content_refs",
            "evidence_refs",
        ]
    return []


__all__ = [
    "CODEX_APPLY_PATCH_RENDERER_ID",
    "CODEX_FINISH_RENDERER_ID",
    "CODEX_TERMINAL_RENDERER_ID",
    "RenderedToolResult",
    "render_observability_record",
    "render_tool_result_for_profile",
]
