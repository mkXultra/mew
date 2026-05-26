from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Optional

from .memory_core import MemoryCompressionRequest, MemoryCompressionResult, MemorySystem


DEFAULT_MEMORY_COMPRESSION_BACKEND = "codex"
DEFAULT_MEMORY_COMPRESSION_MODEL = "gpt-5.5"

ModelJsonCaller = Callable[[str, Mapping[str, Any], str, str, str, int], Any]


def compress_memory_with_model(
    system: MemorySystem,
    request: MemoryCompressionRequest,
    *,
    model_auth: Mapping[str, Any],
    model_backend: str = DEFAULT_MEMORY_COMPRESSION_BACKEND,
    model: str = DEFAULT_MEMORY_COMPRESSION_MODEL,
    base_url: str = "",
    timeout: int = 120,
    call_json: Optional[ModelJsonCaller] = None,
) -> MemoryCompressionResult:
    if model_auth is None:
        raise ValueError("LLM memory compression requires model_auth")
    caller = call_json
    if caller is None:
        from .model_backends import call_model_json

        caller = call_model_json
    payload = caller(
        model_backend,
        model_auth,
        memory_compression_prompt(request),
        model,
        base_url,
        timeout,
    )
    if not isinstance(payload, Mapping):
        raise ValueError("memory compressor model must return a JSON object")
    card = normalize_memory_compression_card(payload, fallback_summary=request.raw_text)
    llm_request = MemoryCompressionRequest(
        raw_text=card["summary"],
        memory_kind=request.memory_kind,
        scope=request.scope,
        source_refs=request.source_refs,
        created_at=request.created_at,
        title_hint=card["title"],
        applicability_hint=card["applicability"],
        validity=request.validity,
        confidence=float(card["confidence"]),
        max_summary_chars=request.max_summary_chars,
        merge_similarity_threshold=request.merge_similarity_threshold,
    )
    return system.compress_memory(llm_request)


def memory_compression_prompt(request: MemoryCompressionRequest) -> str:
    payload = {
        "task": "Compress raw agent/session evidence into one durable memory card.",
        "schema": {
            "title": "short stable label",
            "summary": "one or two compact sentences; preserve only reusable facts",
            "applicability": "when this memory should be recalled",
            "salience": ["novelty", "failure", "success", "review", "decision", "stale", "conflict"],
            "confidence": 0.0,
        },
        "rules": [
            "Return exactly one JSON object matching the schema.",
            "Do not copy raw transcript; compress it.",
            "Prefer new, verified, surprising, repeated, or reviewer-confirmed information.",
            "If details are only evidence, omit them from summary; provenance refs already point to raw data.",
            "Do not invent facts not present in raw_text.",
        ],
        "memory_target": {
            "memory_kind": request.memory_kind,
            "scope": request.scope,
            "title_hint": request.title_hint,
            "applicability_hint": request.applicability_hint,
            "max_summary_chars": request.max_summary_chars,
        },
        "raw_text": request.raw_text,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def normalize_memory_compression_card(payload: Mapping[str, Any], *, fallback_summary: str) -> dict[str, Any]:
    summary = _clean_text(payload.get("summary") or payload.get("memory") or fallback_summary)
    title = _clean_text(payload.get("title") or _first_sentence(summary) or "Compressed memory")
    applicability = _clean_text(payload.get("applicability") or payload.get("when_to_use") or "Use when the same situation recurs.")
    confidence = _coerce_confidence(payload.get("confidence"), default=0.7)
    return {
        "title": _truncate(title, 120),
        "summary": _truncate(summary, 1200),
        "applicability": _truncate(applicability, 400),
        "confidence": confidence,
    }


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _first_sentence(value: str) -> str:
    text = _clean_text(value)
    for separator in (".", "!", "?", "\n"):
        if separator in text:
            return text.split(separator, 1)[0].strip()
    return text


def _truncate(value: str, max_chars: int) -> str:
    text = _clean_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "..."


def _coerce_confidence(value: object, *, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return max(0.0, min(1.0, confidence))
