"""Decision replay packets for explaining implement_v2 model choices.

This module does not replay tools or mutate a workspace. It extracts the
provider-visible state around a selected model decision so a separate model can
explain why that decision was likely made.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from ..model_backends import call_model_json, load_model_auth, model_backend_default_base_url


_MUTATION_TOOLS = frozenset({"apply_patch", "edit_file", "write_file"})
DEFAULT_DECISION_REPLAY_MODEL = "gpt-5.5"
DEFAULT_DECISION_REPLAY_BACKEND = "codex"
DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL = DEFAULT_DECISION_REPLAY_MODEL
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
DEFAULT_COUNTERFACTUAL_ANALYSIS_QUESTION = (
    "At the selected decision point, would these changed instructions likely "
    "change the agent's next action? Predict the next action category and the "
    "smallest visible evidence for that prediction."
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


def build_counterfactual_next_action_packet(
    artifact_root: str | Path,
    *,
    decision_sequence: int | None = None,
    context_items: int = 16,
    counterfactual_instructions: tuple[str, ...] | list[str],
    analysis_question: str | None = None,
    expected_good: tuple[str, ...] | list[str] | None = None,
    expected_bad: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Build a packet for predicting whether prompt/tool-contract changes alter a next action."""

    cleaned_instructions = _clean_text_values(counterfactual_instructions)
    if not cleaned_instructions:
        raise ValueError("at least one counterfactual instruction is required")

    replay_packet = build_decision_replay_packet(
        artifact_root,
        decision_sequence=decision_sequence,
        context_items=context_items,
        analysis_questions=(),
    )
    decision = _mapping(replay_packet.get("decision"))
    selected_sequence = _int(decision.get("sequence"))

    packet = {
        "schema_version": 1,
        "diagnostic": "counterfactual_next_action",
        "artifact_root": replay_packet.get("artifact_root"),
        "provider_requests_path": replay_packet.get("provider_requests_path"),
        "transcript_path": replay_packet.get("transcript_path"),
        "selected_sequence": selected_sequence,
        "original_decision": _action_summary(decision),
        "provider_visible": replay_packet.get("provider_visible") or {},
        "context_before_decision": replay_packet.get("context_before_decision") or [],
        "counterfactual_instructions": cleaned_instructions,
        "counterfactual_prompt_digest": _counterfactual_digest(cleaned_instructions),
        "analysis_question": (analysis_question or DEFAULT_COUNTERFACTUAL_ANALYSIS_QUESTION).strip(),
        "expected_good_categories": _clean_text_values(expected_good or ()),
        "expected_bad_categories": _clean_text_values(expected_bad or ()),
        "prediction_output_contract": {
            "selected_sequence": selected_sequence,
            "original_decision": "compact summary of the observed original next action",
            "counterfactual_prompt_digest": "repeat packet.counterfactual_prompt_digest",
            "predicted_next_action": {
                "tool_name": "predicted tool name or none",
                "command_or_patch_summary": "short visible action summary",
                "target_paths": ["paths the predicted action would touch, if any"],
                "category": "one compact category string",
            },
            "expected_category_match": "good | bad | unknown",
            "likely_effect": "short explanation of whether and how the next action would change",
            "evidence_from_context": ["brief visible evidence strings"],
            "confidence": "low | medium | high",
        },
    }
    return packet


def counterfactual_next_action_prompt(packet: Mapping[str, Any]) -> str:
    """Render a counterfactual next-action packet as a prompt for the analysis model."""

    return (
        "You are reviewing a saved AI coding-agent transcript for a lightweight "
        "counterfactual next-action diagnostic.\n"
        "At the selected_sequence, the original_decision is the observed next action. "
        "Assume the agent reached the same state before that decision, but the "
        "counterfactual_instructions were present in the prompt/tool contract.\n\n"
        "Return only a short JSON object with these keys: selected_sequence, "
        "original_decision, counterfactual_prompt_digest, predicted_next_action, "
        "expected_category_match, likely_effect, evidence_from_context, confidence.\n"
        "predicted_next_action must contain tool_name, command_or_patch_summary, "
        "target_paths, and category. expected_category_match must be good, bad, or "
        "unknown based on packet.expected_good_categories and packet.expected_bad_categories.\n\n"
        "Do not provide hidden chain-of-thought. Use only concise, visible evidence "
        "from the provider-visible prompt/tool contract, context_before_decision, "
        "and the observed original_decision. Do not infer from events that happened "
        "after the selected decision.\n\n"
        "PACKET:\n"
        f"{json.dumps(packet, ensure_ascii=False, indent=2)}\n"
    )


def write_counterfactual_next_action_artifacts(
    artifact_root: str | Path,
    *,
    out_prompt: str | Path,
    decision_sequence: int | None = None,
    context_items: int = 16,
    counterfactual_instructions: tuple[str, ...] | list[str],
    analysis_question: str | None = None,
    expected_good: tuple[str, ...] | list[str] | None = None,
    expected_bad: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Write the counterfactual prompt and return the model-ready packet."""

    packet = build_counterfactual_next_action_packet(
        artifact_root,
        decision_sequence=decision_sequence,
        context_items=context_items,
        counterfactual_instructions=counterfactual_instructions,
        analysis_question=analysis_question,
        expected_good=expected_good,
        expected_bad=expected_bad,
    )
    out_prompt_path = Path(out_prompt)
    out_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    out_prompt_path.write_text(counterfactual_next_action_prompt(packet), encoding="utf-8")
    return packet


def ask_counterfactual_next_action_model(
    packet: Mapping[str, Any],
    *,
    auth_json: str | Path,
    model: str = DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL,
    model_backend: str = DEFAULT_DECISION_REPLAY_BACKEND,
    base_url: str = "",
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Ask a model to predict the next action under counterfactual instructions."""

    auth_path = str(Path(auth_json).expanduser())
    auth = load_model_auth(model_backend, auth_path)
    resolved_base_url = base_url or model_backend_default_base_url(model_backend)
    response = call_model_json(
        model_backend,
        auth,
        counterfactual_next_action_prompt(packet),
        model or DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL,
        resolved_base_url,
        timeout,
    )
    if not isinstance(response, dict):
        raise ValueError("counterfactual next-action model response must be a JSON object")
    return _normalize_counterfactual_response(packet, response)


def counterfactual_next_action(
    artifact_root: str | Path,
    *,
    auth_json: str | Path,
    decision_sequence: int | None = None,
    context_items: int = 16,
    counterfactual_instructions: tuple[str, ...] | list[str],
    analysis_question: str | None = None,
    expected_good: tuple[str, ...] | list[str] | None = None,
    expected_bad: tuple[str, ...] | list[str] | None = None,
    model: str = DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL,
    model_backend: str = DEFAULT_DECISION_REPLAY_BACKEND,
    base_url: str = "",
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Build a counterfactual packet and return the model's JSON prediction."""

    packet = build_counterfactual_next_action_packet(
        artifact_root,
        decision_sequence=decision_sequence,
        context_items=context_items,
        counterfactual_instructions=counterfactual_instructions,
        analysis_question=analysis_question,
        expected_good=expected_good,
        expected_bad=expected_bad,
    )
    return ask_counterfactual_next_action_model(
        packet,
        auth_json=auth_json,
        model=model,
        model_backend=model_backend,
        base_url=base_url,
        timeout=timeout,
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


def _action_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    text = str(item.get("text") or "")
    tool_name = str(item.get("tool_name") or "")
    summary = {
        "sequence": item.get("sequence"),
        "turn_id": item.get("turn_id"),
        "kind": item.get("kind"),
        "tool_name": item.get("tool_name"),
        "status": item.get("status"),
        "is_error": item.get("is_error"),
        "command_or_patch_summary": _command_or_patch_summary(tool_name, text),
        "target_paths": _target_paths(tool_name, text),
        "category": _action_category(tool_name, item.get("kind")),
        "text": _truncate(text, 1600),
    }
    return summary


def _command_or_patch_summary(tool_name: str, text: str) -> str:
    parsed = _json_mapping(text)
    if tool_name == "exec_command":
        command = parsed.get("cmd") or parsed.get("command") or text
        return _truncate(str(command), 600)
    if tool_name in _MUTATION_TOOLS or "*** Begin Patch" in text:
        paths = _target_paths(tool_name, text)
        if paths:
            return _truncate(f"patch touching {', '.join(paths)}", 600)
        return _truncate(text, 600)
    return _truncate(text, 600)


def _target_paths(tool_name: str, text: str) -> list[str]:
    if tool_name != "exec_command" and "*** Begin Patch" in text:
        paths = []
        for line in text.splitlines():
            match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)", line)
            if match:
                paths.append(match.group(1).strip())
        return sorted(dict.fromkeys(paths))
    parsed = _json_mapping(text)
    path_values = parsed.get("paths") or parsed.get("target_paths")
    if isinstance(path_values, list):
        return [str(path) for path in path_values if str(path).strip()]
    return []


def _action_category(tool_name: str, kind: object) -> str:
    if tool_name in _MUTATION_TOOLS:
        return "workspace_mutation"
    if tool_name == "exec_command":
        return "shell_command"
    if "read" in tool_name or tool_name in {"open", "find", "ls"}:
        return "read_or_inspect"
    if not tool_name and not kind:
        return "unknown"
    return "other_tool_action"


def _counterfactual_digest(instructions: list[str]) -> str:
    payload = json.dumps(instructions, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _clean_text_values(values: tuple[str, ...] | list[str]) -> list[str]:
    cleaned = []
    for value in values:
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _json_mapping(text: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, Mapping) else {}


def _normalize_counterfactual_response(
    packet: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = dict(response)
    normalized.setdefault("selected_sequence", packet.get("selected_sequence"))
    normalized.setdefault("original_decision", packet.get("original_decision"))
    normalized.setdefault("counterfactual_prompt_digest", packet.get("counterfactual_prompt_digest"))
    if "predicted_next_action" not in normalized:
        normalized["predicted_next_action"] = {
            "tool_name": "",
            "command_or_patch_summary": "",
            "target_paths": [],
            "category": "unknown",
        }
    normalized.setdefault("expected_category_match", "unknown")
    normalized.setdefault("likely_effect", "")
    normalized.setdefault("evidence_from_context", [])
    normalized.setdefault("confidence", "low")
    return normalized


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
    "DEFAULT_COUNTERFACTUAL_ANALYSIS_QUESTION",
    "DEFAULT_COUNTERFACTUAL_NEXT_ACTION_MODEL",
    "DEFAULT_DECISION_REPLAY_BACKEND",
    "DEFAULT_DECISION_REPLAY_MODEL",
    "ask_decision_replay_model",
    "ask_counterfactual_next_action_model",
    "build_decision_replay_packet",
    "build_counterfactual_next_action_packet",
    "counterfactual_next_action",
    "counterfactual_next_action_prompt",
    "decision_replay_prompt",
    "write_counterfactual_next_action_artifacts",
    "write_decision_replay_artifacts",
]
