"""Compare provider-visible request shape across saved native artifacts.

The comparison is artifact-only: it reads saved provider request JSON and
reports model-visible prompt/input signals.  It is intended for regression
triage when two commits produce different implement_v2 step flow.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from .provider_visible_salience import (
    _input_item_texts,
    _mapping,
    _read_json_mapping,
    _resolve_provider_requests_path,
    _sequence,
)

PROVIDER_VISIBLE_ARTIFACT_COMPARE_SCHEMA_VERSION = 1
PROVIDER_VISIBLE_ARTIFACT_COMPARE_REPORT_KIND = "m6_24_provider_visible_artifact_compare"

SIGNAL_TERMS: tuple[tuple[str, str], ...] = (
    ("coding_contract_section", "Implement V2 Coding Contract"),
    ("environment_context_section", "Implement V2 Environment Context"),
    ("minimal_runnable_candidate", "minimal runnable candidate"),
    ("missing_path_guidance", "missing source or artifact path"),
    ("task_facts_key", "task_facts"),
    ("missing_workspace_paths_key", "missing_workspace_paths"),
    ("missing_task_paths_label", "Missing task paths"),
    ("existing_task_paths_label", "Existing task paths"),
    ("verifier_paths_label", "Verifier paths"),
    ("source_connected_build_path", "source-connected build path"),
    ("developer_tool_contract", "codex_hot_path tool surface"),
    ("manual_apply_patch_contract", "Use apply_patch for manual source edits."),
    ("raw_task_only_contract", "raw_task"),
)


def compare_provider_visible_artifacts(
    *,
    artifacts: Sequence[tuple[str, object]],
) -> dict[str, object]:
    """Return a compact provider-visible request comparison report."""

    rows = [_artifact_row(label=str(label), artifact_root=root) for label, root in artifacts]
    return {
        "schema_version": PROVIDER_VISIBLE_ARTIFACT_COMPARE_SCHEMA_VERSION,
        "report_kind": PROVIDER_VISIBLE_ARTIFACT_COMPARE_REPORT_KIND,
        "sidecar_only": True,
        "provider_visible_behavior_changed": False,
        "signal_terms": {key: term for key, term in SIGNAL_TERMS},
        "artifact_count": len(rows),
        "artifacts": rows,
        "diff_summary": _diff_summary(rows),
    }


def write_provider_visible_artifact_compare_report(
    *,
    artifacts: Sequence[tuple[str, object]],
    out_json: object,
    out_md: object,
) -> dict[str, object]:
    """Write JSON and Markdown provider-visible comparison reports."""

    report = compare_provider_visible_artifacts(artifacts=artifacts)
    json_path = Path(str(out_json)).expanduser()
    md_path = Path(str(out_md)).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_provider_visible_artifact_compare_markdown(report) + "\n", encoding="utf-8")
    return report


def format_provider_visible_artifact_compare_markdown(report: Mapping[str, object]) -> str:
    """Render a human-readable provider-visible comparison."""

    rows = [_mapping(item) for item in _sequence(report.get("artifacts"))]
    lines = [
        "# Provider-Visible Artifact Compare",
        "",
        "Artifact-only diagnostic. This report does not call a model or change live behavior.",
        "",
        "## Request Shape",
        "",
        "| Label | Requests | Roles | Instructions chars | Input text chars | Sections | JSON keys |",
        "|---|---:|---|---:|---:|---|---|",
    ]
    for row in rows:
        first = _mapping(row.get("first_request"))
        lines.append(
            "| "
            f"{_md(str(row.get('label') or ''))} | "
            f"{int(row.get('request_count') or 0)} | "
            f"`{_md(', '.join(str(item) for item in first.get('input_roles') or []))}` | "
            f"{int(first.get('instructions_chars') or 0)} | "
            f"{int(first.get('input_text_chars') or 0)} | "
            f"`{_md(', '.join(str(item) for item in first.get('model_visible_sections') or []))}` | "
            f"`{_md(', '.join(str(item) for item in first.get('json_payload_keys') or []))}` |"
        )

    lines.extend(
        [
            "",
            "## Signal Matrix",
            "",
            "| Signal | " + " | ".join(_md(str(row.get("label") or "")) for row in rows) + " |",
            "|---|" + "|".join("---:" for _ in rows) + "|",
        ]
    )
    signal_keys = [key for key, _term in SIGNAL_TERMS]
    for key in signal_keys:
        cells = []
        for row in rows:
            first = _mapping(row.get("first_request"))
            counts = _mapping(first.get("signal_counts"))
            cells.append(str(int(counts.get(key) or 0)))
        lines.append(f"| `{_md(key)}` | " + " | ".join(cells) + " |")

    lines.extend(["", "## Diff Summary", ""])
    for item in _sequence(report.get("diff_summary")):
        lines.append(f"- {item}")
    return "\n".join(lines)


def _artifact_row(*, label: str, artifact_root: object) -> dict[str, object]:
    root = Path(str(artifact_root)).expanduser()
    provider_requests_path = _resolve_provider_requests_path(root)
    raw = _read_json_mapping(provider_requests_path)
    requests = tuple(_mapping(item) for item in _sequence(raw.get("requests")))
    first = _first_request_row(requests[0]) if requests else {}
    return {
        "label": label,
        "artifact_root": str(root.resolve(strict=False)),
        "native_provider_requests": str(provider_requests_path.resolve(strict=False)),
        "request_count": len(requests),
        "first_request": first,
    }


def _first_request_row(request: Mapping[str, object]) -> dict[str, object]:
    body = _mapping(request.get("request_body"))
    input_source = body.get("input") or request.get("input_items")
    input_items = tuple(_mapping(item) for item in _sequence(input_source))
    text_blob = "\n".join((str(body.get("instructions") or ""), *_input_item_texts(input_items)))
    json_payload = _first_json_payload(input_items)
    return {
        "turn_index": int(request.get("turn_index") or 0),
        "tool_surface_profile_id": str(request.get("tool_surface_profile_id") or ""),
        "input_roles": [str(item.get("role") or "") for item in input_items],
        "instructions_chars": len(str(body.get("instructions") or "")),
        "input_text_chars": sum(len(text) for text in _input_item_texts(input_items)),
        "model_visible_sections": _model_visible_sections(request),
        "instruction_section_ids": _instruction_section_ids(str(body.get("instructions") or "")),
        "json_payload_keys": list(json_payload.keys()),
        "signal_counts": _signal_counts(text_blob, request=request),
        "first_user_text_preview": _preview(_first_user_text(input_items)),
    }


def _signal_counts(text: str, *, request: Mapping[str, object]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for key, term in SIGNAL_TERMS:
        count = text.count(term)
        if count:
            counts[key] = count
    sections = _model_visible_sections(request)
    if "raw_task" in sections and not any(section in sections for section in ("task_context", "task_facts")):
        counts["raw_task_only_contract"] += 1
    return {key: int(counts.get(key, 0)) for key, _term in SIGNAL_TERMS}


def _first_json_payload(input_items: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    for text in _input_item_texts(input_items):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            return value
    return {}


def _first_user_text(input_items: Sequence[Mapping[str, object]]) -> str:
    for item in input_items:
        if item.get("role") != "user":
            continue
        for text in _input_item_texts((item,)):
            if text.strip():
                return text
    return ""


def _instruction_section_ids(instructions: str) -> list[str]:
    return re.findall(r"\[section:([^\s\]]+)", instructions)


def _model_visible_sections(request: Mapping[str, object]) -> list[str]:
    inventory = _mapping(request.get("provider_request_inventory"))
    sections = inventory.get("model_visible_sections")
    return [str(item) for item in _sequence(sections)]


def _diff_summary(rows: Sequence[Mapping[str, object]]) -> list[str]:
    if len(rows) < 2:
        return ["Need at least two artifacts to summarize differences."]
    first = _mapping(rows[0].get("first_request"))
    last = _mapping(rows[-1].get("first_request"))
    first_counts = _mapping(first.get("signal_counts"))
    last_counts = _mapping(last.get("signal_counts"))
    notes: list[str] = []
    for key, _term in SIGNAL_TERMS:
        before = int(first_counts.get(key) or 0)
        after = int(last_counts.get(key) or 0)
        if before and not after:
            notes.append(f"`{key}` is present in `{rows[0].get('label')}` but absent in `{rows[-1].get('label')}`.")
        elif after and not before:
            notes.append(f"`{key}` is absent in `{rows[0].get('label')}` but present in `{rows[-1].get('label')}`.")
    if not notes:
        notes.append("No tracked first-request signal changed between the first and last artifacts.")
    return notes


def _preview(text: str, *, limit: int = 220) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 3]}..."


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "PROVIDER_VISIBLE_ARTIFACT_COMPARE_REPORT_KIND",
    "PROVIDER_VISIBLE_ARTIFACT_COMPARE_SCHEMA_VERSION",
    "SIGNAL_TERMS",
    "compare_provider_visible_artifacts",
    "format_provider_visible_artifact_compare_markdown",
    "write_provider_visible_artifact_compare_report",
]
