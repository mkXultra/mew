"""Artifact-only provider-visible salience diagnostics for M6.24.

The analyzer reads saved native provider request artifacts and reports what the
model saw.  It never calls a model and never changes live loop behavior.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

PROVIDER_VISIBLE_SALIENCE_SCHEMA_VERSION = 1
PROVIDER_VISIBLE_SALIENCE_REPORT_KIND = "m6_24_provider_visible_salience"

SCAFFOLDING_TERMS: tuple[str, ...] = (
    "compact_sidecar_digest",
    "native_sidecar_digest",
    "provider_input_authority",
    "provider_request_note",
    "sidecar_hashes",
    "source_of_truth",
    "latest_evidence_refs",
    "latest_tool_results",
    "digest_hash",
    "transcript_hash",
    "runtime_id",
    "lane_attempt_id",
    "evidence_refs",
    "output_refs",
    "tool-result:",
    "implement-v2-evidence://",
    "implement-v2-exec://",
)

TASK_ANCHOR_KEYS: tuple[str, ...] = (
    "verify_command_paths",
    "mentioned_workspace_paths",
    "missing_workspace_paths",
    "existing_workspace_paths",
)


def analyze_provider_visible_salience(*, mew_artifact_root: object) -> dict[str, object]:
    """Analyze saved native provider requests for prompt/transcript salience."""

    root = Path(str(mew_artifact_root)).expanduser()
    provider_requests_path = _resolve_provider_requests_path(root)
    inventory_search_root = provider_requests_path.parent
    inventory_path = _resolve_optional(inventory_search_root, "provider-request-inventory.json")
    raw = _read_json_mapping(provider_requests_path)
    requests = tuple(_mapping(item) for item in _sequence(raw.get("requests")))
    inventories = _load_inventories(inventory_path)

    request_reports = tuple(
        _request_report(index=index + 1, request=request, inventory=_inventory_at(inventories, index))
        for index, request in enumerate(requests)
    )
    aggregate = _aggregate_reports(request_reports)
    return {
        "schema_version": PROVIDER_VISIBLE_SALIENCE_SCHEMA_VERSION,
        "report_kind": PROVIDER_VISIBLE_SALIENCE_REPORT_KIND,
        "sidecar_only": True,
        "provider_visible_behavior_changed": False,
        "inputs": {
            "mew_artifact_root": str(root.resolve(strict=False)),
            "native_provider_requests": str(provider_requests_path.resolve(strict=False)),
            "provider_request_inventory": str(inventory_path.resolve(strict=False)) if inventory_path else None,
        },
        "request_count": len(request_reports),
        "scaffolding_terms": list(SCAFFOLDING_TERMS),
        "aggregate": aggregate,
        "first_request": request_reports[0] if request_reports else {},
        "turns": list(request_reports),
        "interpretation": _interpretation(aggregate, request_reports),
    }


def write_provider_visible_salience_report(
    *,
    mew_artifact_root: object,
    out_json: object,
    out_md: object,
) -> dict[str, object]:
    """Build and write JSON plus Markdown provider-visible salience reports."""

    report = analyze_provider_visible_salience(mew_artifact_root=mew_artifact_root)
    json_path = Path(str(out_json)).expanduser()
    md_path = Path(str(out_md)).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_provider_visible_salience_markdown(report) + "\n", encoding="utf-8")
    return report


def format_provider_visible_salience_markdown(report: Mapping[str, object]) -> str:
    """Render a compact Markdown handoff report."""

    inputs = _mapping(report.get("inputs"))
    aggregate = _mapping(report.get("aggregate"))
    first = _mapping(report.get("first_request"))
    lines = [
        "# M6.24 Provider-Visible Salience",
        "",
        "Artifact-only diagnostic. This report does not affect live mew behavior.",
        "",
        "## Inputs",
        "",
        f"- mew artifact root: `{_md(str(inputs.get('mew_artifact_root') or ''))}`",
        f"- native provider requests: `{_md(str(inputs.get('native_provider_requests') or ''))}`",
        f"- provider request inventory: `{_md(str(inputs.get('provider_request_inventory') or ''))}`",
        "",
        "## Summary",
        "",
        f"- Requests: {int(report.get('request_count') or 0)}",
        f"- First request leading shape: `{_md(str(first.get('leading_shape') or 'unknown'))}`",
        f"- First request top-level section order: `{_md(', '.join(str(item) for item in first.get('top_level_section_order') or []))}`",
        f"- Requests with visible compact sidecar digest: {int(aggregate.get('compact_sidecar_visible_request_count') or 0)}",
        f"- Max first input text chars: {int(aggregate.get('max_first_input_text_chars') or 0)}",
        f"- Max compact sidecar JSON chars: {int(aggregate.get('max_compact_sidecar_chars') or 0)}",
        f"- Total scaffolding term occurrences: {int(aggregate.get('scaffolding_occurrences_total') or 0)}",
        "",
        "## Scaffolding Terms",
        "",
        "| Term | Count |",
        "|---|---:|",
    ]
    for term, count in _sorted_counter(_mapping(aggregate.get("scaffolding_occurrences_by_term"))):
        lines.append(f"| `{_md(term)}` | {count} |")
    if not aggregate.get("scaffolding_occurrences_by_term"):
        lines.append("| none | 0 |")

    lines.extend(["", "## First Ten Requests", "", "| Turn | Shape | Text chars | Sidecar chars | Scaffolding | Task anchors |", "|---:|---|---:|---:|---:|---:|"])
    for row in [item for item in report.get("turns") or [] if isinstance(item, Mapping)][:10]:
        lines.append(
            f"| {int(row.get('turn_index') or 0)} | `{_md(str(row.get('leading_shape') or 'unknown'))}` | "
            f"{int(row.get('first_input_text_chars') or 0)} | "
            f"{int(row.get('compact_sidecar_chars') or 0)} | "
            f"{int(row.get('scaffolding_occurrences') or 0)} | "
            f"{int(row.get('task_anchor_occurrences') or 0)} |"
        )

    lines.extend(["", "## Interpretation", ""])
    for item in report.get("interpretation") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _request_report(*, index: int, request: Mapping[str, object], inventory: Mapping[str, object]) -> dict[str, object]:
    body = _mapping(request.get("request_body"))
    input_items = tuple(_mapping(item) for item in _sequence(body.get("input")))
    first_text = _first_input_text(input_items)
    task_payload = _first_json_payload(input_items)
    section_order = list(task_payload.keys())
    compact_sidecar = _mapping(task_payload.get("compact_sidecar_digest"))
    task_facts = _mapping(task_payload.get("task_facts"))
    task_contract = _mapping(task_payload.get("task_contract"))
    visible_text = "\n".join(
        text
        for text in (
            str(body.get("instructions") or ""),
            *(_input_item_texts(input_items)),
        )
        if text
    )
    scaffolding_counts = _count_terms(visible_text, SCAFFOLDING_TERMS)
    task_anchor_terms = tuple(_task_anchor_terms(task_facts))
    task_anchor_counts = _count_terms(visible_text, task_anchor_terms)
    sidecar_visible = bool(
        inventory.get("compact_sidecar_digest_wire_visible", "compact_sidecar_digest" in task_payload)
    )
    return {
        "turn_index": int(request.get("turn_index") or index),
        "previous_response_id_in_request_body": bool(request.get("previous_response_id_in_request_body")),
        "input_item_count": len(input_items),
        "instructions_chars": len(str(body.get("instructions") or "")),
        "first_input_text_chars": len(first_text),
        "leading_shape": _leading_shape(first_text),
        "json_payload_found": bool(task_payload),
        "top_level_section_order": section_order,
        "top_level_section_chars": {key: _json_chars(value) for key, value in task_payload.items()},
        "task_description_chars": len(str(task_contract.get("description") or "")),
        "task_guidance_chars": len(str(task_contract.get("guidance") or "")),
        "task_anchor_terms": list(task_anchor_terms),
        "task_anchor_occurrences": sum(task_anchor_counts.values()),
        "task_anchor_occurrences_by_term": dict(task_anchor_counts),
        "compact_sidecar_visible": sidecar_visible,
        "compact_sidecar_chars": _json_chars(compact_sidecar),
        "compact_sidecar_digest_text_chars": len(str(compact_sidecar.get("digest_text") or "")),
        "compact_sidecar_key_count": len(compact_sidecar),
        "compact_sidecar_keys": list(compact_sidecar.keys()),
        "latest_tool_results_count": len(_sequence(compact_sidecar.get("latest_tool_results"))),
        "latest_evidence_refs_count": len(_sequence(compact_sidecar.get("latest_evidence_refs"))),
        "scaffolding_occurrences": sum(scaffolding_counts.values()),
        "scaffolding_occurrences_by_term": dict(scaffolding_counts),
    }


def _aggregate_reports(reports: Sequence[Mapping[str, object]]) -> dict[str, object]:
    scaffolding = Counter[str]()
    task_anchors = Counter[str]()
    for report in reports:
        scaffolding.update({str(key): int(value) for key, value in _mapping(report.get("scaffolding_occurrences_by_term")).items()})
        task_anchors.update({str(key): int(value) for key, value in _mapping(report.get("task_anchor_occurrences_by_term")).items()})
    return {
        "request_count": len(reports),
        "compact_sidecar_visible_request_count": sum(1 for report in reports if report.get("compact_sidecar_visible")),
        "json_envelope_request_count": sum(1 for report in reports if report.get("leading_shape") == "json_envelope"),
        "plain_text_first_request_count": sum(1 for report in reports if report.get("leading_shape") == "plain_text"),
        "json_payload_request_count": sum(1 for report in reports if report.get("json_payload_found")),
        "max_first_input_text_chars": max((int(report.get("first_input_text_chars") or 0) for report in reports), default=0),
        "max_compact_sidecar_chars": max((int(report.get("compact_sidecar_chars") or 0) for report in reports), default=0),
        "max_scaffolding_occurrences": max((int(report.get("scaffolding_occurrences") or 0) for report in reports), default=0),
        "scaffolding_occurrences_total": sum(scaffolding.values()),
        "scaffolding_occurrences_by_term": dict(sorted(scaffolding.items())),
        "task_anchor_occurrences_total": sum(task_anchors.values()),
        "task_anchor_occurrences_by_term": dict(sorted(task_anchors.items())),
    }


def _interpretation(aggregate: Mapping[str, object], reports: Sequence[Mapping[str, object]]) -> list[str]:
    notes: list[str] = []
    request_count = int(aggregate.get("request_count") or 0)
    if request_count == 0:
        return ["No provider requests were found; H7/H1 cannot be evaluated from this artifact."]
    if int(aggregate.get("json_envelope_request_count") or 0) == request_count:
        notes.append("H1 is measurable: every first user item is a JSON envelope, not a plain task-first message.")
    if int(aggregate.get("plain_text_first_request_count") or 0) == request_count:
        notes.append("H1 task-first shape is present: every first user item is plain text before the JSON support payload.")
    if int(aggregate.get("compact_sidecar_visible_request_count") or 0) == request_count:
        notes.append("H7 is measurable: compact_sidecar_digest is visible on every saved provider request.")
    if int(aggregate.get("scaffolding_occurrences_total") or 0) > int(aggregate.get("task_anchor_occurrences_total") or 0):
        notes.append("Scaffolding vocabulary appears more often than task-anchor vocabulary in the provider-visible text.")
    first = reports[0] if reports else {}
    order = [str(item) for item in first.get("top_level_section_order") or []]
    if order and order[:2] != ["task_contract", "task_facts"]:
        notes.append(f"First-request section order starts with {order[:2]}, so task content is not the leading payload.")
    notes.append("This diagnostic is evidence for selecting a next experiment only; it does not authorize behavior changes by itself.")
    return notes


def _load_inventories(path: Path | None) -> tuple[Mapping[str, object], ...]:
    if path is None:
        return ()
    raw = _read_json_mapping(path)
    rows = raw.get("provider_request_inventory")
    return tuple(_mapping(item) for item in _sequence(rows))


def _inventory_at(inventories: Sequence[Mapping[str, object]], index: int) -> Mapping[str, object]:
    if 0 <= index < len(inventories):
        return inventories[index]
    return {}


def _resolve_provider_requests_path(root: Path) -> Path:
    direct = root if root.name == "native-provider-requests.json" else root / "native-provider-requests.json"
    if direct.is_file():
        return direct
    matches = sorted(root.glob("**/native-provider-requests.json"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"native-provider-requests.json not found under {root}")


def _resolve_optional(root: Path, filename: str) -> Path | None:
    direct = root / filename
    if direct.is_file():
        return direct
    matches = sorted(root.glob(f"**/{filename}"))
    return matches[0] if matches else None


def _read_json_mapping(path: Path) -> Mapping[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _input_item_texts(items: Iterable[Mapping[str, object]]) -> tuple[str, ...]:
    texts: list[str] = []
    for item in items:
        for content in _sequence(item.get("content")):
            content_map = _mapping(content)
            text = content_map.get("text")
            if isinstance(text, str):
                texts.append(text)
    return tuple(texts)


def _first_input_text(items: Sequence[Mapping[str, object]]) -> str:
    for text in _input_item_texts(items):
        if text.strip():
            return text
    return ""


def _first_json_payload(items: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    for text in _input_item_texts(items):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    return {}


def _leading_shape(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json_envelope"
    if stripped:
        return "plain_text"
    return "empty"


def _task_anchor_terms(task_facts: Mapping[str, object]) -> tuple[str, ...]:
    terms: list[str] = []
    for key in TASK_ANCHOR_KEYS:
        for value in _sequence(task_facts.get(key)):
            text = str(value).strip()
            if text and text not in terms:
                terms.append(text)
    return tuple(terms)


def _count_terms(text: str, terms: Sequence[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for term in terms:
        if not term:
            continue
        count = text.count(term)
        if count:
            counts[term] = count
    return counts


def _json_chars(value: object) -> int:
    if value in ({}, [], None):
        return 0
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    return tuple(value) if isinstance(value, (list, tuple)) else ()


def _sorted_counter(value: Mapping[str, object]) -> list[tuple[str, int]]:
    return sorted(((str(key), int(count)) for key, count in value.items()), key=lambda item: (-item[1], item[0]))


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "\\`")


__all__ = [
    "PROVIDER_VISIBLE_SALIENCE_REPORT_KIND",
    "PROVIDER_VISIBLE_SALIENCE_SCHEMA_VERSION",
    "SCAFFOLDING_TERMS",
    "analyze_provider_visible_salience",
    "format_provider_visible_salience_markdown",
    "write_provider_visible_salience_report",
]
