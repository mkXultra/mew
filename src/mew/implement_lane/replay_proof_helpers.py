"""Native replay/proof helpers shared by production replay and legacy diagnostics."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
import re

from .execution_evidence import normalize_execution_contract
from .finish_acceptance_helpers import _artifact_id_is_visual_runtime_output, _is_verifier_scratch_artifact_id
from .types import ToolResultEnvelope

_FRONTIER_LIST_LIMIT = 8
_FRONTIER_TEXT_LIMIT = 500
_SOURCE_OUTPUT_CONTRACT_PATH_RE = re.compile(
    r"(?P<path>(?:/[A-Za-z0-9._@%+=:,~-]+)+\."
    r"(?:bmp|png|jpe?g|gif|ppm|pgm|pbm|json|csv|txt|log|dat|bin|out|wasm|pdf|html|xml))"
)
_SOURCE_OUTPUT_CONTRACT_CONTEXT_MARKERS = frozenset(
    {
        "artifact",
        "create",
        "created",
        "export",
        "frame",
        "fopen",
        "fwrite",
        "generate",
        "generated",
        "image",
        "open(",
        "output",
        "produce",
        "produced",
        "render",
        "rendered",
        "result",
        "save",
        "saved",
        "saving",
        "write",
        "writefile",
        "writes",
        "written",
    }
)
_SOURCE_OUTPUT_DECLARATION_RE = re.compile(
    r"(?im)^\s*(?:export\s+)?"
    r"(?:OUTPUT|OUTPUT_FILE|OUTPUT_PATH|OUT_FILE|OUT_PATH|TARGET|TARGET_NAME|BINARY|EXECUTABLE|ARTIFACT|IMAGE|FRAME)"
    r"\s*(?::=|\?=|\+=|=)\s*[\"']?(?P<value>[A-Za-z0-9._@%+=,~/-]{1,200})"
)


def _frontier_evidence_registry(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    artifact_namespace: str,
) -> dict[str, object]:
    output_refs: set[str] = set()
    command_run_ids: set[str] = set()
    for result in tool_results:
        for item in result.content:
            if not isinstance(item, dict):
                continue
            if item.get("command_run_id"):
                command_run_ids.add(str(item.get("command_run_id")))
            if item.get("output_ref"):
                output_refs.add(str(item.get("output_ref")))
    return {
        "tool_call_ids": set(range(1, len(tool_results) + 1)),
        "provider_call_ids": {result.provider_call_id for result in tool_results if result.provider_call_id},
        "command_run_ids": command_run_ids,
        "output_refs": output_refs,
        "content_refs": {ref for result in tool_results for ref in result.content_refs},
        "evidence_refs": {ref for result in tool_results for ref in result.evidence_refs},
        "artifact_namespace": artifact_namespace,
    }


def _source_output_contract_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    registry: dict[str, object],
) -> dict[str, object]:
    best: dict[str, object] = {}
    best_score = -1
    for result in tool_results:
        if result.tool_name not in {"read_file", "search_text", "run_command", "run_tests"}:
            continue
        payload = next((item for item in result.content if isinstance(item, dict)), {})
        if not payload:
            continue
        raw_contract = payload.get("execution_contract")
        contract = _payload_execution_contract(payload)
        if isinstance(raw_contract, dict) and contract and _execution_contract_is_verifier_like(contract):
            continue
        for text, source_label in _source_output_contract_texts(result.tool_name, payload):
            for candidate in _source_output_contract_candidates(text, source_label=source_label):
                score = int(candidate.get("_score") or 0)
                if score <= best_score:
                    continue
                refs = _frontier_result_refs(result, registry)
                candidate.pop("_score", None)
                if refs:
                    candidate["evidence_refs"] = refs
                best = candidate
                best_score = score
    return best


def _frontier_result_refs(result: ToolResultEnvelope, registry: dict[str, object]) -> list[dict[str, object]]:
    return _resolve_frontier_refs([*result.evidence_refs, *result.content_refs], registry)


def _resolve_frontier_refs(value: object, registry: dict[str, object]) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value[: _FRONTIER_LIST_LIMIT * 2]:
        normalized = _normalize_frontier_ref(item, registry)
        if not normalized:
            continue
        key = json.dumps(normalized, ensure_ascii=True, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        refs.append(normalized)
        if len(refs) >= _FRONTIER_LIST_LIMIT:
            break
    return refs


def _normalize_frontier_ref(item: object, registry: dict[str, object]) -> dict[str, object] | None:
    if isinstance(item, dict):
        kind = str(item.get("kind") or "").strip()
        if kind == "tool_call":
            try:
                tool_id = int(item.get("id"))
            except (TypeError, ValueError):
                return None
            return {"kind": "tool_call", "id": tool_id} if tool_id in registry["tool_call_ids"] else None
        if kind == "provider_call":
            provider_id = str(item.get("id") or "").strip()
            return {"kind": "provider_call", "id": provider_id} if provider_id in registry["provider_call_ids"] else None
        if kind == "command_run":
            command_run_id = str(item.get("id") or "").strip()
            return {"kind": "command_run", "id": command_run_id} if command_run_id in registry["command_run_ids"] else None
        if kind == "command_output":
            output_ref = str(item.get("ref") or "").strip()
            return {"kind": "command_output", "ref": output_ref} if output_ref in registry["output_refs"] else None
        if kind == "content_ref":
            content_ref = str(item.get("ref") or "").strip()
            return {"kind": "content_ref", "ref": content_ref} if content_ref in registry["content_refs"] else None
        if kind == "evidence_ref":
            evidence_ref = str(item.get("ref") or "").strip()
            return {"kind": "evidence_ref", "ref": evidence_ref} if evidence_ref in registry["evidence_refs"] else None
        if kind == "proof_artifact":
            path = str(item.get("path") or "").strip()
            namespace = str(registry.get("artifact_namespace") or "")
            if _proof_artifact_ref_resolves(path, namespace=namespace):
                return {"kind": "proof_artifact", "path": path}
            return None
        return None
    if isinstance(item, str):
        ref = item.strip()
        if ref in registry["content_refs"]:
            return {"kind": "content_ref", "ref": ref}
        if ref in registry["evidence_refs"]:
            return {"kind": "evidence_ref", "ref": ref}
        if ref in registry["output_refs"]:
            return {"kind": "command_output", "ref": ref}
    return None


def _proof_artifact_ref_resolves(path: str, *, namespace: str) -> bool:
    if not path or not namespace:
        return False
    normalized_text = path.replace("\\", "/")
    while normalized_text.startswith("./"):
        normalized_text = normalized_text[2:]
    normalized = PurePosixPath(normalized_text)
    namespace_path = PurePosixPath(namespace)
    if normalized.is_absolute() or ".." in normalized.parts or ".." in namespace_path.parts:
        return False
    namespace_parts = namespace_path.parts
    return len(normalized.parts) > len(namespace_parts) and normalized.parts[: len(namespace_parts)] == namespace_parts


def _payload_execution_contract(payload: dict[str, object]) -> dict[str, object]:
    raw = payload.get("execution_contract")
    raw_contract = raw if isinstance(raw, dict) else {}
    normalized = payload.get("execution_contract_normalized")
    normalized_contract = normalized if isinstance(normalized, dict) else {}
    merged = {**raw_contract, **normalized_contract}
    if not merged:
        return {}
    contract = normalize_execution_contract(merged).as_dict()
    raw_artifact_alias_keys = {"expected_artifact", "final_artifact", "artifacts", "expected_artifacts"}
    suppress_raw_artifact_aliases = bool(payload.get("unchecked_expected_artifacts")) and bool(normalized_contract)
    for source in (normalized_contract, raw_contract):
        for key, value in source.items():
            if source is raw_contract and suppress_raw_artifact_aliases and key in raw_artifact_alias_keys:
                continue
            if key not in contract:
                contract[key] = value
    return contract


def _execution_contract_enum(contract: dict[str, object], key: str) -> str:
    return str(contract.get(key) or "").strip().lower()


def _execution_contract_is_runtime_like(contract: dict[str, object]) -> bool:
    role = _execution_contract_enum(contract, "role")
    if role == "build":
        return False
    return (
        role == "runtime"
        or _execution_contract_enum(contract, "purpose") in {"runtime_build", "runtime_install", "smoke", "verification"}
        or _execution_contract_enum(contract, "stage")
        in {"runtime_build", "runtime_install", "default_smoke", "custom_runtime_smoke", "verification"}
        or _execution_contract_enum(contract, "proof_role")
        in {"runtime_install", "default_smoke", "custom_runtime_smoke", "verifier"}
        or _execution_contract_enum(contract, "acceptance_kind") == "external_verifier"
    )


def _execution_contract_is_verifier_like(contract: dict[str, object]) -> bool:
    return (
        _execution_contract_is_runtime_like(contract)
        or _execution_contract_enum(contract, "purpose") in {"artifact_proof", "verification"}
        or _execution_contract_enum(contract, "stage") in {"artifact_proof", "verification"}
        or _execution_contract_enum(contract, "proof_role") in {"final_artifact", "verifier"}
        or _execution_contract_enum(contract, "acceptance_kind") in {"candidate_final_proof", "external_verifier"}
    )


def _source_output_contract_texts(tool_name: str, payload: dict[str, object]) -> tuple[tuple[str, str], ...]:
    texts: list[tuple[str, str]] = []
    if tool_name == "read_file":
        for nested in _source_output_contract_payload_items(payload):
            path = _frontier_clip_text(nested.get("path"), limit=240)
            label = f"read_file:{path}" if path else "read_file"
            for key in ("text", "summary"):
                value = str(nested.get(key) or "")
                if value.strip():
                    texts.append((value, label))
        return tuple(texts)
    if tool_name == "search_text":
        for nested in _source_output_contract_payload_items(payload):
            for key in ("matches", "snippets", "text", "summary"):
                value = nested.get(key)
                if isinstance(value, list):
                    serialized = "\n".join(_source_output_contract_search_item_text(item) for item in value)
                elif isinstance(value, dict):
                    serialized = _source_output_contract_search_item_text(value)
                else:
                    serialized = str(value or "")
                if serialized.strip():
                    texts.append((serialized, "search_text"))
        return tuple(texts)
    for nested in _source_output_contract_payload_items(payload):
        for key in ("stdout", "stdout_tail", "stderr", "stderr_tail", "summary"):
            value = str(nested.get(key) or "")
            if value.strip():
                texts.append((value, tool_name))
    return tuple(texts)


def _source_output_contract_search_item_text(item: object) -> str:
    if not isinstance(item, dict):
        return str(item or "")
    chunks = []
    for key in ("text", "line", "content", "snippet", "match", "summary"):
        value = item.get(key)
        if value:
            chunks.append(str(value))
    return "\n".join(chunks)


def _source_output_contract_payload_items(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    items = []
    if not _source_output_contract_payload_item_is_verifier_like(payload):
        items.append(payload)
    nested = payload.get("content")
    if isinstance(nested, list):
        items.extend(
            item
            for item in nested
            if isinstance(item, dict) and not _source_output_contract_payload_item_is_verifier_like(item)
        )
    return tuple(items)


def _source_output_contract_payload_item_is_verifier_like(payload: dict[str, object]) -> bool:
    raw_contract = payload.get("execution_contract")
    normalized_contract = payload.get("execution_contract_normalized")
    if not isinstance(raw_contract, dict) and not isinstance(normalized_contract, dict):
        return False
    return bool(_execution_contract_is_verifier_like(_payload_execution_contract(payload)))


def _source_output_contract_candidates(text: str, *, source_label: str) -> tuple[dict[str, object], ...]:
    candidates: list[dict[str, object]] = []
    for match in _SOURCE_OUTPUT_CONTRACT_PATH_RE.finditer(text or ""):
        path = match.group("path").strip()
        if not path or _is_verifier_scratch_artifact_id(path):
            continue
        if _source_output_contract_path_is_search_location(text, match):
            continue
        window = text[max(0, match.start() - 160) : min(len(text), match.end() + 160)]
        window_lower = window.casefold()
        marker_hits = sorted(marker for marker in _SOURCE_OUTPUT_CONTRACT_CONTEXT_MARKERS if marker in window_lower)
        if not marker_hits:
            continue
        score = 2 + min(len(marker_hits), 4)
        if _artifact_id_is_visual_runtime_output(path):
            score += 3
        if source_label.startswith(("read_file", "search_text")):
            score += 2
        if any(token in window_lower for token in (".c:", ".cc:", ".cpp:", ".h:", "printf", "fopen", "writefile")):
            score += 1
        candidates.append(
            _drop_empty_frontier_values(
                {
                    "path": _frontier_clip_text(path, limit=400),
                    "kind": _source_output_contract_kind(path),
                    "source": "source_or_probe_output",
                    "confidence": "high" if score >= 6 else "medium",
                    "source_label": _frontier_clip_text(source_label, limit=160),
                    "evidence_excerpt": _frontier_clip_text(" ".join(window.split()), limit=240),
                    "markers": marker_hits[:6],
                    "_score": score,
                }
            )
        )
    return tuple(candidates)


def _text_has_source_output_declaration(text: str) -> bool:
    for match in _SOURCE_OUTPUT_DECLARATION_RE.finditer(text or ""):
        value = str(match.group("value") or "").strip().strip("'\"`")
        if value and not value.startswith(("-", "$")) and not _is_verifier_scratch_artifact_id(value):
            return True
    return False


def _source_output_label_is_source_read(source_label: str) -> bool:
    if not source_label.startswith("read_file") or ":" not in source_label:
        return False
    return _shell_path_is_source_like(source_label.split(":", 1)[1])


def _text_has_source_output_surface(text: str) -> bool:
    value = str(text or "")
    if not value.strip():
        return False
    return _text_matches_any(
        value,
        (
            r"\b(?:draw|render|present|display|paint|save)[A-Za-z0-9_]*\s*\(",
            r"\b(?:SDL_UpdateTexture|SDL_RenderPresent|DG_DrawFrame|save_frame)\b",
        ),
    ) and _text_matches_any(
        value,
        (
            r"\b(?:frame|image|screen|canvas|texture|pixel|framebuffer|surface|buffer)\b",
            r"\b(?:RGB|RGBA|BMP|PPM|PNG|JPEG|bitmap|rendered)\b",
        ),
    )


def _source_output_contract_path_is_search_location(text: str, match: re.Match[str]) -> bool:
    suffix = text[match.end() : match.end() + 16]
    return bool(re.match(r":\d+(?::|-|$)", suffix))


def _source_output_contract_kind(path: str) -> str:
    lowered = path.casefold()
    if lowered.endswith((".bmp", ".png", ".jpg", ".jpeg", ".gif", ".ppm", ".pgm", ".pbm")):
        return "image"
    if lowered.endswith((".json", ".csv", ".txt", ".log", ".html", ".xml")):
        return "file"
    if lowered.endswith((".bin", ".out", ".wasm")):
        return "binary"
    return "file"


def _shell_path_is_source_like(path: object) -> bool:
    raw = str(path or "").strip().strip("'\"")
    if not raw or raw.startswith(("-", "$")) or raw.startswith(("/tmp/", "tmp/")):
        return False
    name = PurePosixPath(raw).name
    if name in {
        "Makefile",
        "Dockerfile",
        "CMakeLists.txt",
        "Cargo.toml",
        "Cargo.lock",
        "go.mod",
        "go.sum",
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "pom.xml",
        "build.gradle",
        "settings.gradle",
    }:
        return True
    return PurePosixPath(name).suffix.casefold() in {
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".hh",
        ".rs",
        ".go",
        ".py",
        ".js",
        ".ts",
        ".java",
        ".kt",
        ".swift",
        ".zig",
        ".s",
        ".asm",
        ".wat",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    }


def _text_matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _frontier_clip_text(value: object, *, limit: int = _FRONTIER_TEXT_LIMIT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 35)]}...<truncated {len(text) - max(0, limit - 35)} chars>"


def _drop_empty_frontier_values(value: dict[str, object]) -> dict[str, object]:
    return {str(key): item for key, item in value.items() if item not in (None, "", [], {})}


__all__ = [
    "_frontier_evidence_registry",
    "_source_output_contract_from_tool_results",
]
