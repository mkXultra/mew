"""Shared implementation-lane contract types.

These dataclasses are deliberately small and serializable. They are the
boundary that lets implement_v1 and implement_v2 evolve independently while
still producing comparable artifacts for M6.24.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Literal

from .affordance_visibility import CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS

TOOL_CALL_SCHEMA_VERSION = 1
TOOL_RESULT_SCHEMA_VERSION = 1
PROOF_MANIFEST_SCHEMA_VERSION = 1
_VISIBLE_TOOL_OUTPUT_CARD_HARD_BYTES = 6144
_MUTATION_VISIBLE_CARD_HARD_BYTES = 4096
_NATURAL_RESULT_TEXT_LIMIT = 1200
_VISIBLE_PATH_CHARS = 260
_VISIBLE_REF_CHARS = 160
_FORBIDDEN_VISIBLE_FIELD_SET = frozenset(CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS)

TranscriptEventKind = Literal[
    "model_message",
    "tool_call",
    "tool_result",
    "approval",
    "verifier",
    "finish",
]

ToolCallStatus = Literal["received", "validated", "rejected", "executing", "completed"]
ToolResultStatus = Literal[
    "completed",
    "failed",
    "denied",
    "invalid",
    "interrupted",
    "running",
    "yielded",
]


@dataclass(frozen=True)
class ImplementLaneInput:
    """Minimum input passed into an implementation lane runtime."""

    work_session_id: str
    task_id: str
    workspace: str
    lane: str
    model_backend: str = ""
    model: str = ""
    effort: str = ""
    task_contract: dict[str, object] = field(default_factory=dict)
    lane_config: dict[str, object] = field(default_factory=dict)
    persisted_lane_state: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "work_session_id": self.work_session_id,
            "task_id": self.task_id,
            "workspace": self.workspace,
            "lane": self.lane,
            "model_backend": self.model_backend,
            "model": self.model,
            "effort": self.effort,
            "task_contract": dict(self.task_contract),
            "lane_config": dict(self.lane_config),
            "persisted_lane_state": dict(self.persisted_lane_state),
        }


@dataclass(frozen=True)
class ToolCallEnvelope:
    """Provider-neutral representation of one provider-native tool call."""

    lane_attempt_id: str
    provider: str
    provider_call_id: str
    mew_tool_call_id: str
    tool_name: str
    arguments: dict[str, object] = field(default_factory=dict)
    provider_message_id: str = ""
    turn_index: int = 0
    sequence_index: int = 0
    raw_arguments_ref: str = ""
    received_at: str = ""
    status: ToolCallStatus = "received"
    schema_version: int = field(default=TOOL_CALL_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane_attempt_id": self.lane_attempt_id,
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "provider_call_id": self.provider_call_id,
            "mew_tool_call_id": self.mew_tool_call_id,
            "turn_index": self.turn_index,
            "sequence_index": self.sequence_index,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "raw_arguments_ref": self.raw_arguments_ref,
            "received_at": self.received_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class ToolResultEnvelope:
    """Provider-neutral representation of the paired result for a tool call."""

    lane_attempt_id: str
    provider_call_id: str
    mew_tool_call_id: str
    tool_name: str
    status: ToolResultStatus
    is_error: bool = False
    content: tuple[object, ...] = ()
    content_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    side_effects: tuple[dict[str, object], ...] = ()
    route_decision: dict[str, object] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    schema_version: int = field(default=TOOL_RESULT_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane_attempt_id": self.lane_attempt_id,
            "provider_call_id": self.provider_call_id,
            "mew_tool_call_id": self.mew_tool_call_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "is_error": self.is_error,
            "content": list(self.content),
            "content_refs": list(self.content_refs),
            "evidence_refs": list(self.evidence_refs),
            "side_effects": [dict(effect) for effect in self.side_effects],
            "route_decision": dict(self.route_decision),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def provider_visible_content(self) -> dict[str, object]:
        """Return content suitable for provider tool_result payloads."""

        card = self.visible_tool_output_card()
        return {
            "mew_status": self.status,
            "acceptance_evidence": bool(self.evidence_refs) and self.status == "completed",
            "natural_result_text": self.natural_result_text(),
            "tool_output_card": card,
            "content": list(self.content),
            "content_refs": list(self.content_refs),
            "output_refs": list(self.content_refs),
            "evidence_refs": list(self.evidence_refs),
            "side_effects": [dict(effect) for effect in self.side_effects],
            "route_decision": dict(self.route_decision),
        }

    def visible_tool_output_card(self) -> dict[str, object]:
        """Return a bounded factual card for model-visible tool output."""

        payload = self.content[0] if self.content and isinstance(self.content[0], dict) else {}
        status_parts = [f"{self.tool_name or 'tool'} result: {self.status}"]
        if self.is_error:
            status_parts.append("error=true")
        for key in ("status", "exit_code", "path", "command_run_id", "failure_class", "failure_kind"):
            value = payload.get(key)
            if value not in (None, "", [], {}):
                status_parts.append(f"{key}={_scalar_preview(value, limit=120)}")
        if self.tool_name == "search_text" and isinstance(payload.get("matches"), list):
            status_parts.append(f"matches={len(payload.get('matches') or [])}")
        summary = payload.get("summary")
        if summary not in (None, "", [], {}):
            status_parts.append(f"summary={_scalar_preview(summary, limit=120)}")
        card: dict[str, object] = {
            "schema_version": 1,
            "tool_name": self.tool_name,
            "status": self.status,
            "is_error": self.is_error,
            "status_line": _clip_preview("; ".join(status_parts), limit=240),
            "paths": _visible_tool_paths(self.tool_name, payload),
            "refs": _visible_tool_refs(self.content_refs, self.evidence_refs),
        }
        latest_failure = _visible_latest_failure(self.tool_name, payload, is_error=self.is_error, status=self.status)
        if latest_failure:
            card["latest_failure"] = latest_failure
        output_tail = _visible_output_tail(self.tool_name, payload)
        if output_tail:
            card["output_tail"] = output_tail
        excerpt = _visible_read_excerpt(self.tool_name, payload)
        if excerpt:
            card["excerpt"] = excerpt
        search_anchors = _search_text_anchor_preview(payload)
        if search_anchors:
            card["anchors"] = search_anchors
        mutation = _visible_mutation_card(payload)
        if mutation:
            card["mutation"] = mutation
        return _fit_visible_tool_output_card(_drop_empty_card_values(card))

    def natural_result_text(self, *, limit: int = _NATURAL_RESULT_TEXT_LIMIT) -> str:
        """Return a compact natural-language result for the next model turn."""

        text = _render_visible_tool_output_card(self.visible_tool_output_card())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."


def _command_output_preview(tool_name: str, payload: dict[str, object], *, limit: int = 900) -> str:
    if tool_name not in {"run_command", "run_tests", "poll_command", "cancel_command"}:
        return ""
    stderr = _text_payload(payload.get("stderr"))
    stderr_tail = _text_payload(payload.get("stderr_tail"))
    stdout = _text_payload(payload.get("stdout"))
    stdout_tail = _text_payload(payload.get("stdout_tail"))
    streams = [
        ("stderr_preview", stderr, stderr_tail),
        ("stdout_preview", stdout, stdout_tail),
    ]
    present = [(label, text, tail) for label, text, tail in streams if text.strip() or tail.strip()]
    if present:
        per_stream_limit = max(220, (limit - max(0, len(present) - 1) * 2) // len(present))
        rendered = [
            f"{label}: {_head_tail_preview(text or tail, tail if text else '', limit=per_stream_limit)}"
            for label, text, tail in present
        ]
        return _clip_preview("; ".join(rendered), limit=limit)
    return ""


def _head_tail_preview(text: str, tail: str = "", *, limit: int) -> str:
    raw_text = str(text or "").strip()
    raw_tail = str(tail or "").strip()
    first_line = raw_text.splitlines()[0].strip() if raw_text else ""
    text = " ".join(raw_text.split())
    tail = " ".join(raw_tail.split())
    if not text and not tail:
        return ""
    if not tail:
        return _clip_preview(text or tail, limit=limit)
    if len(text) <= limit and tail in text:
        return text
    if len(text) > limit * 2 and first_line:
        first_line = " ".join(first_line.split())
        head_limit = max(80, min(180, limit // 4))
        tail_limit = max(180, limit - head_limit - 22)
        return f"{_clip_preview(first_line, limit=head_limit)} ... tail: {_clip_preview(tail, limit=tail_limit)}"
    head_limit = max(120, limit // 2)
    tail_limit = max(120, limit - head_limit - 22)
    return f"{_clip_preview(text, limit=head_limit)} ... tail: {_clip_preview(tail, limit=tail_limit)}"


def _clip_preview(text: str, *, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _text_payload(value: object) -> str:
    return value if isinstance(value, str) else ""


def _render_visible_tool_output_card(card: dict[str, object]) -> str:
    parts = [str(card.get("status_line") or "").strip()]
    paths = card.get("paths")
    if isinstance(paths, list) and paths:
        parts.append("paths: " + ", ".join(str(path) for path in paths[:12]))
    latest_failure = str(card.get("latest_failure") or "").strip()
    if latest_failure:
        parts.append("latest_failure: " + latest_failure)
    output_tail = str(card.get("output_tail") or "").strip()
    if output_tail:
        parts.append("output_tail: " + output_tail)
    excerpt = str(card.get("excerpt") or "").strip()
    if excerpt:
        parts.append("excerpt:\n" + excerpt)
    anchors = str(card.get("anchors") or "").strip()
    if anchors:
        parts.append(anchors)
    mutation = card.get("mutation") if isinstance(card.get("mutation"), dict) else {}
    if mutation:
        parts.append("mutation: " + _render_mutation_summary(mutation))
    refs = card.get("refs")
    if isinstance(refs, list) and refs:
        parts.append("refs: " + ",".join(str(ref) for ref in refs[:12]))
    return "; ".join(part for part in parts if part)


def _render_mutation_summary(mutation: dict[str, object]) -> str:
    parts = []
    for key in ("operation", "status", "changed_paths", "diff_ref", "mutation_ref", "diff_stats"):
        value = mutation.get(key)
        if value not in (None, "", [], {}):
            parts.append(f"{key}={_scalar_preview(value, limit=260)}")
    return "; ".join(parts)


def _visible_tool_paths(tool_name: str, payload: dict[str, object]) -> list[str]:
    paths: list[str] = []
    for value in payload.get("changed_paths") if isinstance(payload.get("changed_paths"), list) else []:
        _append_visible_path(paths, value)
    mutation = payload.get("mutation_output_card") if isinstance(payload.get("mutation_output_card"), dict) else {}
    if isinstance(mutation, dict):
        for value in mutation.get("changed_paths") if isinstance(mutation.get("changed_paths"), list) else []:
            _append_visible_path(paths, value)
    path = str(payload.get("path") or "").strip()
    if path:
        if tool_name == "read_file":
            line_start = payload.get("line_start")
            line_end = payload.get("line_end")
            if line_start not in (None, ""):
                suffix = f":{line_start}"
                if line_end not in (None, "", line_start):
                    suffix += f"-{line_end}"
                _append_visible_path(paths, f"{path}{suffix}")
            else:
                _append_visible_path(paths, path)
        else:
            _append_visible_path(paths, path)
    for snippet in payload.get("snippets") or ():
        if not isinstance(snippet, dict):
            continue
        snippet_path = str(snippet.get("path") or "").strip()
        line = snippet.get("start_line") or snippet.get("line")
        if snippet_path:
            _append_visible_path(paths, f"{snippet_path}:{line}" if line not in (None, "") else snippet_path)
        if len(paths) >= 12:
            break
    return paths[:12]


def _visible_tool_refs(content_refs: tuple[str, ...], evidence_refs: tuple[str, ...]) -> list[str]:
    refs: list[str] = []
    for ref in (*content_refs, *evidence_refs):
        text = _scalar_preview(ref, limit=_VISIBLE_REF_CHARS)
        if text and text not in refs:
            refs.append(text)
        if len(refs) >= 12:
            break
    return refs


def _visible_latest_failure(tool_name: str, payload: dict[str, object], *, is_error: bool, status: str) -> str:
    explicit = payload.get("latest_failure")
    if isinstance(explicit, dict):
        return _clip_preview(_compact_mapping_text(explicit), limit=1200)
    if isinstance(explicit, str) and explicit.strip():
        return _clip_preview(_redact_forbidden_visible_markers(" ".join(explicit.strip().split())), limit=1200)
    failed = is_error or status in {"failed", "invalid", "denied", "interrupted"}
    if not failed:
        return ""
    facts = []
    for key in ("failure_class", "failure_kind", "reason", "message", "error", "exit_code"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            facts.append(f"{key}={_scalar_preview(value, limit=200)}")
    for key in ("stderr_tail", "stderr", "stdout_tail", "stdout"):
        text = _text_payload(payload.get(key)).strip()
        if text:
            facts.append(f"{key}: {_redact_forbidden_visible_markers(' '.join(text.split()))}")
            break
    return _clip_preview("; ".join(facts), limit=1200)


def _visible_output_tail(tool_name: str, payload: dict[str, object]) -> str:
    command_preview = _command_output_preview(tool_name, payload, limit=1200)
    if command_preview:
        return command_preview
    for key in ("stderr_tail", "stdout_tail", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            tail = "\n".join(value.strip().splitlines()[-20:])
            return _head_tail_preview(value, tail, limit=1200)
    return ""


def _visible_read_excerpt(tool_name: str, payload: dict[str, object]) -> str:
    if tool_name != "read_file":
        return ""
    text = _text_payload(payload.get("text"))
    if not text.strip():
        return ""
    path = str(payload.get("path") or "").strip()
    start = payload.get("line_start")
    try:
        line_no = int(start) if start not in (None, "") else 1
    except (TypeError, ValueError):
        line_no = 1
    lines = []
    for raw in text.splitlines()[:160]:
        clipped = raw[:220]
        prefix = f"{path}:{line_no}: " if path else f"{line_no}: "
        lines.append(prefix + clipped)
        line_no += 1
    return _clip_preview("\n".join(lines), limit=3500)


def _visible_mutation_card(payload: dict[str, object]) -> dict[str, object]:
    mutation = payload.get("mutation_output_card") if isinstance(payload.get("mutation_output_card"), dict) else {}
    if not isinstance(mutation, dict) or not mutation:
        return {}
    return _fit_mutation_visible_card(
        _drop_empty_card_values(
        {
            "operation": _scalar_preview(mutation.get("operation"), limit=80),
            "status": _scalar_preview(mutation.get("status"), limit=80),
            "changed_paths": [
                _scalar_preview(path, limit=_VISIBLE_PATH_CHARS)
                for path in list(mutation.get("changed_paths") or [])[:12]
            ]
            if isinstance(mutation.get("changed_paths"), list)
            else [],
            "diff_ref": _scalar_preview(mutation.get("diff_ref"), limit=_VISIBLE_REF_CHARS),
            "mutation_ref": _scalar_preview(mutation.get("mutation_ref"), limit=_VISIBLE_REF_CHARS),
            "diff_stats": _compact_mapping_text(mutation.get("diff_stats") or {}, limit=1000)
            if isinstance(mutation.get("diff_stats"), dict)
            else "",
        }
        )
    )


def _drop_empty_card_values(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}


def _append_visible_path(paths: list[str], value: object) -> None:
    text = _scalar_preview(value, limit=_VISIBLE_PATH_CHARS)
    if text and text not in paths:
        paths.append(text)


def _compact_mapping_text(value: dict[str, object], *, limit: int = 1200) -> str:
    parts = []
    for key, item in value.items():
        key_text = str(key)
        if _is_forbidden_visible_key(key_text) or item in (None, "", [], {}):
            continue
        parts.append(f"{key_text}={_scalar_preview(item, limit=220)}")
    return _clip_preview("; ".join(parts), limit=limit)


def _fit_visible_tool_output_card(card: dict[str, object]) -> dict[str, object]:
    fitted = _redact_forbidden_visible_fields(dict(card))
    if isinstance(fitted.get("paths"), list):
        fitted["paths"] = [_scalar_preview(path, limit=_VISIBLE_PATH_CHARS) for path in fitted["paths"][:12]]
    if isinstance(fitted.get("refs"), list):
        fitted["refs"] = [_scalar_preview(ref, limit=_VISIBLE_REF_CHARS) for ref in fitted["refs"][:12]]
    mutation = fitted.get("mutation") if isinstance(fitted.get("mutation"), dict) else {}
    if mutation:
        fitted["mutation"] = _fit_mutation_visible_card(mutation)
    if _json_size_bytes(fitted) <= _VISIBLE_TOOL_OUTPUT_CARD_HARD_BYTES:
        return fitted
    for key in ("excerpt", "output_tail", "latest_failure", "anchors", "status_line"):
        if isinstance(fitted.get(key), str):
            fitted[key] = _clip_preview(str(fitted[key]), limit=900 if key != "status_line" else 240)
        if _json_size_bytes(fitted) <= _VISIBLE_TOOL_OUTPUT_CARD_HARD_BYTES:
            return fitted
    if isinstance(fitted.get("paths"), list):
        fitted["paths"] = list(fitted["paths"])[:6]
    if isinstance(fitted.get("refs"), list):
        fitted["refs"] = list(fitted["refs"])[:6]
    if _json_size_bytes(fitted) <= _VISIBLE_TOOL_OUTPUT_CARD_HARD_BYTES:
        return fitted
    for key in ("excerpt", "output_tail", "anchors", "latest_failure", "mutation"):
        fitted.pop(key, None)
        if _json_size_bytes(fitted) <= _VISIBLE_TOOL_OUTPUT_CARD_HARD_BYTES:
            return fitted
    fitted["card_truncated"] = True
    return _force_fit_mapping(fitted, _VISIBLE_TOOL_OUTPUT_CARD_HARD_BYTES)


def _fit_mutation_visible_card(card: dict[str, object]) -> dict[str, object]:
    fitted = _redact_forbidden_visible_fields(dict(card))
    if isinstance(fitted.get("changed_paths"), list):
        fitted["changed_paths"] = [
            _scalar_preview(path, limit=_VISIBLE_PATH_CHARS) for path in fitted["changed_paths"][:12]
        ]
    if isinstance(fitted.get("diff_stats"), str):
        fitted["diff_stats"] = _clip_preview(str(fitted["diff_stats"]), limit=400)
    if _json_size_bytes(fitted) <= _MUTATION_VISIBLE_CARD_HARD_BYTES:
        return fitted
    if isinstance(fitted.get("changed_paths"), list):
        fitted["changed_paths"] = list(fitted["changed_paths"])[:6]
    for key in ("diff_stats", "diff_ref", "mutation_ref"):
        if isinstance(fitted.get(key), str):
            fitted[key] = _clip_preview(str(fitted[key]), limit=180)
        if _json_size_bytes(fitted) <= _MUTATION_VISIBLE_CARD_HARD_BYTES:
            return fitted
    return _force_fit_mapping(fitted, _MUTATION_VISIBLE_CARD_HARD_BYTES)


def _redact_forbidden_visible_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): _redact_forbidden_visible_fields(item)
            for key, item in value.items()
            if not _is_forbidden_visible_key(str(key))
        }
    if isinstance(value, list):
        return [_redact_forbidden_visible_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_forbidden_visible_fields(item) for item in value)
    if isinstance(value, str):
        return _redact_forbidden_visible_markers(value)
    return value


def _redact_forbidden_visible_markers(text: str) -> str:
    cleaned = str(text)
    for field_name in sorted(_FORBIDDEN_VISIBLE_FIELD_SET, key=len, reverse=True):
        cleaned = cleaned.replace(field_name, "[redacted]")
    return cleaned


def _is_forbidden_visible_key(key: str) -> bool:
    return key in _FORBIDDEN_VISIBLE_FIELD_SET


def _force_fit_mapping(value: dict[str, object], limit: int) -> dict[str, object]:
    fitted = dict(value)
    if _json_size_bytes(fitted) <= limit:
        return fitted
    for key in list(fitted):
        if key in {"schema_version", "tool_name", "status", "is_error", "status_line", "card_truncated"}:
            continue
        fitted.pop(key, None)
        if _json_size_bytes(fitted) <= limit:
            return fitted
    if isinstance(fitted.get("status_line"), str):
        fitted["status_line"] = _clip_preview(str(fitted["status_line"]), limit=160)
    while _json_size_bytes(fitted) > limit and fitted:
        key = next(reversed(fitted))
        if key == "schema_version":
            break
        fitted.pop(key, None)
    return fitted


def _json_size_bytes(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def _scalar_preview(value: object, *, limit: int) -> str:
    if value in (None, "", [], {}):
        return ""
    text = str(_redact_forbidden_visible_fields(value))
    text = " ".join(text.strip().split())
    return _clip_preview(text, limit=limit)


def _search_text_anchor_preview(payload: dict[str, object], *, limit: int = 850) -> str:
    """Expose compact path:line anchors for model-visible search results.

    Full search payloads remain sidecar-backed, but a native function-call
    output that only says "matches=50" forces the next model turn to guess or
    repeat the same search. Keep a small, generic rg-like preview so the model
    can choose a narrow read_file on the discovered file.
    """

    lines: list[str] = []
    for snippet in payload.get("snippets") or ():
        if not isinstance(snippet, dict):
            continue
        path = str(snippet.get("path") or "").strip()
        if not path:
            continue
        for item in snippet.get("lines") or ():
            if not isinstance(item, dict) or not item.get("match"):
                continue
            line = str(item.get("line") or "").strip()
            text = " ".join(str(item.get("text") or "").strip().split())
            if line:
                lines.append(f"{path}:{line}:{text[:220]}")
            if len(lines) >= 8:
                break
        if len(lines) >= 8:
            break
    if not lines:
        for match in payload.get("matches") or ():
            text = " ".join(str(match or "").strip().split())
            if not text:
                continue
            lines.append(text[:320])
            if len(lines) >= 8:
                break
    if not lines:
        return ""
    preview = "search_anchors:\n" + "\n".join(lines)
    if len(preview) <= limit:
        return preview
    clipped_lines: list[str] = []
    used = len("search_anchors:\n")
    for line in lines:
        remaining = limit - used
        if remaining <= 20:
            break
        clipped = line[: max(0, remaining - 1)]
        clipped_lines.append(clipped)
        used += len(clipped) + 1
    return "search_anchors:\n" + "\n".join(clipped_lines)


def search_text_output_has_line_anchor(text: object) -> bool:
    """Return whether a model-visible search result includes a path:line anchor."""

    return bool(re.search(r"(?m)(?:^|[\s;])\S[^:\n;]*:\d+:", str(text or "")))


@dataclass(frozen=True)
class ImplementLaneTranscriptEvent:
    """Replayable transcript event emitted by an implementation lane."""

    kind: TranscriptEventKind
    lane: str
    turn_id: str
    event_id: str
    payload: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "lane": self.lane,
            "turn_id": self.turn_id,
            "event_id": self.event_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class ImplementLaneProofManifest:
    """Minimum v2 proof manifest shape for replay and M6.24 attribution."""

    lane: str
    lane_attempt_id: str
    artifact_namespace: str
    tool_calls: tuple[ToolCallEnvelope, ...] = ()
    tool_results: tuple[ToolResultEnvelope, ...] = ()
    metrics: dict[str, object] = field(default_factory=dict)
    schema_version: int = field(default=PROOF_MANIFEST_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane": self.lane,
            "lane_attempt_id": self.lane_attempt_id,
            "artifact_namespace": self.artifact_namespace,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "tool_results": [result.as_dict() for result in self.tool_results],
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class ImplementLaneResult:
    """Comparable result shape for implementation lane runtimes."""

    status: str
    lane: str
    user_visible_summary: str = ""
    proof_artifacts: tuple[str, ...] = ()
    next_reentry_hint: dict[str, object] = field(default_factory=dict)
    updated_lane_state: dict[str, object] = field(default_factory=dict)
    metrics: dict[str, object] = field(default_factory=dict)
    transcript: tuple[ImplementLaneTranscriptEvent, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "lane": self.lane,
            "user_visible_summary": self.user_visible_summary,
            "proof_artifacts": list(self.proof_artifacts),
            "next_reentry_hint": dict(self.next_reentry_hint),
            "updated_lane_state": dict(self.updated_lane_state),
            "metrics": dict(self.metrics),
            "transcript": [event.as_dict() for event in self.transcript],
        }


__all__ = [
    "ImplementLaneInput",
    "ImplementLaneProofManifest",
    "ImplementLaneResult",
    "ImplementLaneTranscriptEvent",
    "PROOF_MANIFEST_SCHEMA_VERSION",
    "TOOL_CALL_SCHEMA_VERSION",
    "TOOL_RESULT_SCHEMA_VERSION",
    "TranscriptEventKind",
    "ToolCallEnvelope",
    "ToolCallStatus",
    "ToolResultEnvelope",
    "ToolResultStatus",
]
