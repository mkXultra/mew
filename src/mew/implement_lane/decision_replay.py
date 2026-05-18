"""Decision replay packets for explaining implement_v2 model choices.

This module does not replay tools or mutate a workspace. It extracts the
provider-visible state around a selected model decision so a separate model can
explain why that decision was likely made.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..model_backends import call_model_json, load_model_auth, model_backend_default_base_url


_MUTATION_TOOLS = frozenset({"apply_patch", "edit_file", "write_file"})
DEFAULT_DECISION_REPLAY_MODEL = "gpt-5.5"
DEFAULT_DECISION_REPLAY_BACKEND = "codex"
DEFAULT_ANALYSIS_QUESTIONS = (
    "What should the original coding agent have done instead for this task?",
    (
        "Is the smallest useful repair a prompt/affordance change, a tool-surface "
        "change, or a runtime/controller change? Explain why."
    ),
    (
        "What generic change would reduce this failure without overfitting to this "
        "specific benchmark task?"
    ),
)


def build_decision_replay_packet(
    artifact_root: str | Path,
    *,
    decision_sequence: int | None = None,
    context_items: int = 16,
    analysis_questions: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Build a compact packet for asking an LLM why a model chose an action."""

    root = Path(artifact_root)
    provider_requests_path = _find_artifact_path(root, "native-provider-requests.json")
    transcript_path = _find_artifact_path(root, "response_transcript.json")

    provider_requests = _read_json(provider_requests_path)
    transcript = _read_json(transcript_path)
    requests = provider_requests.get("requests")
    if not isinstance(requests, list) or not requests:
        raise ValueError(f"native-provider-requests.json has no requests: {provider_requests_path}")
    items = transcript.get("items")
    if not isinstance(items, list):
        raise ValueError(f"response_transcript.json has no items: {transcript_path}")

    decision = _select_decision_item(items, decision_sequence=decision_sequence)
    decision_seq = int(decision.get("sequence") or 0)
    before = [
        _compact_transcript_item(item)
        for item in items
        if _int(item.get("sequence")) < decision_seq
    ][-max(1, context_items) :]
    after = [
        _compact_transcript_item(item)
        for item in items
        if _int(item.get("sequence")) > decision_seq
    ][:4]

    first_request = requests[0]
    request_body = first_request.get("request_body") if isinstance(first_request, Mapping) else {}
    if not isinstance(request_body, Mapping):
        request_body = {}
    tools = []
    for tool in request_body.get("tools") or ():
        if not isinstance(tool, Mapping):
            continue
        tools.append(str(tool.get("name") or _mapping(tool.get("function")).get("name") or tool.get("type") or ""))

    packet = {
        "schema_version": 1,
        "artifact_root": str(root),
        "provider_requests_path": str(provider_requests_path),
        "transcript_path": str(transcript_path),
        "provider_visible": {
            "instructions": str(request_body.get("instructions") or ""),
            "initial_input": request_body.get("input") or [],
            "tools": [tool for tool in tools if tool],
        },
        "decision": _compact_transcript_item(decision),
        "context_before_decision": before,
        "context_after_decision": after,
        "question": (
            "Explain why the model likely chose this decision from the provider-visible "
            "prompt and transcript. Distinguish prompt/tool-surface causes from task "
            "evidence. If the decision is a synthetic replacement instead of a "
            "source-preserving patch, identify the transcript evidence that pushed it "
            "there and the smallest generic change that would have made the model choose "
            "the source-preserving path."
        ),
        "analysis_questions": _analysis_questions(analysis_questions),
    }
    return packet


def decision_replay_prompt(packet: Mapping[str, Any]) -> str:
    """Render a packet as a prompt for an external analysis model."""

    return (
        "You are reviewing an AI coding-agent decision from a saved native tool transcript.\n"
        "Return concise JSON with keys: decision_summary, likely_causes, evidence, "
        "counterfactual_changes, answers, confidence, and whether_more_live_runs_are_needed.\n"
        "The answers object must answer each item from packet.analysis_questions by index.\n\n"
        "Do not invent hidden chain-of-thought. Use only the visible prompt, tool calls, "
        "tool outputs, and patch text in this packet.\n\n"
        "PACKET:\n"
        f"{json.dumps(packet, ensure_ascii=False, indent=2)}\n"
    )


def write_decision_replay_artifacts(
    artifact_root: str | Path,
    *,
    out_json: str | Path,
    out_prompt: str | Path,
    decision_sequence: int | None = None,
    context_items: int = 16,
    analysis_questions: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Write a decision replay packet and LLM prompt."""

    packet = build_decision_replay_packet(
        artifact_root,
        decision_sequence=decision_sequence,
        context_items=context_items,
        analysis_questions=analysis_questions,
    )
    out_json_path = Path(out_json)
    out_prompt_path = Path(out_prompt)
    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_prompt_path.write_text(decision_replay_prompt(packet), encoding="utf-8")
    return packet


def ask_decision_replay_model(
    packet: Mapping[str, Any],
    *,
    auth_json: str | Path,
    model: str = DEFAULT_DECISION_REPLAY_MODEL,
    model_backend: str = DEFAULT_DECISION_REPLAY_BACKEND,
    base_url: str = "",
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Ask a model to explain a decision replay packet.

    The replay script intentionally requires an explicit auth path so diagnostic
    runs are reproducible across context compaction and do not silently switch
    between local auth files.
    """

    auth_path = str(Path(auth_json).expanduser())
    auth = load_model_auth(model_backend, auth_path)
    resolved_base_url = base_url or model_backend_default_base_url(model_backend)
    response = call_model_json(
        model_backend,
        auth,
        decision_replay_prompt(packet),
        model or DEFAULT_DECISION_REPLAY_MODEL,
        resolved_base_url,
        timeout,
    )
    if not isinstance(response, dict):
        raise ValueError("decision replay model response must be a JSON object")
    return dict(response)


def _select_decision_item(
    items: list[Any],
    *,
    decision_sequence: int | None,
) -> Mapping[str, Any]:
    if decision_sequence is not None:
        for item in items:
            if isinstance(item, Mapping) and _int(item.get("sequence")) == decision_sequence:
                return item
        raise ValueError(f"decision sequence not found: {decision_sequence}")
    for item in items:
        if not isinstance(item, Mapping):
            continue
        tool_name = str(item.get("tool_name") or "")
        if tool_name in _MUTATION_TOOLS and item.get("kind") in {"function_call", "custom_tool_call"}:
            return item
    raise ValueError("no mutation decision found; pass --decision-sequence explicitly")


def _compact_transcript_item(item: Mapping[str, Any]) -> dict[str, Any]:
    text = str(
        item.get("arguments_json_text")
        or item.get("custom_input_text")
        or item.get("output_text_or_ref")
        or item.get("summary")
        or item.get("text")
        or ""
    )
    return {
        "sequence": item.get("sequence"),
        "turn_id": item.get("turn_id"),
        "kind": item.get("kind"),
        "tool_name": item.get("tool_name"),
        "call_id": item.get("call_id"),
        "status": item.get("status"),
        "is_error": item.get("is_error"),
        "text": _truncate(text, 8000),
        "content_refs": item.get("content_refs") or [],
        "evidence_refs": item.get("evidence_refs") or [],
    }


def _analysis_questions(extra_questions: tuple[str, ...] | list[str] | None) -> list[str]:
    questions = list(DEFAULT_ANALYSIS_QUESTIONS)
    for question in extra_questions or ():
        cleaned = str(question).strip()
        if cleaned:
            questions.append(cleaned)
    return questions


def _find_artifact_path(root: Path, filename: str) -> Path:
    if root.is_file():
        if root.name == filename:
            return root
        sibling = root.parent / filename
        if sibling.exists():
            return sibling
    direct = root / filename
    if direct.exists():
        return direct
    matches = sorted(root.rglob(filename)) if root.exists() else []
    if not matches:
        raise FileNotFoundError(f"{filename} not found under {root}")
    return matches[0]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


__all__ = [
    "DEFAULT_ANALYSIS_QUESTIONS",
    "DEFAULT_DECISION_REPLAY_BACKEND",
    "DEFAULT_DECISION_REPLAY_MODEL",
    "ask_decision_replay_model",
    "build_decision_replay_packet",
    "decision_replay_prompt",
    "write_decision_replay_artifacts",
]
