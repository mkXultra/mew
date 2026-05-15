"""Artifact-only output compaction diagnostics for M6.24.

The audit compares raw saved tool results with the function-call output text
that was actually sent back to the provider. It never calls a model and never
changes live loop behavior.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

OUTPUT_COMPACTION_AUDIT_SCHEMA_VERSION = 1
OUTPUT_COMPACTION_AUDIT_REPORT_KIND = "m6_24_output_compaction_audit"

CRITICAL_FACT_CATEGORIES = frozenset({"paths", "errors", "symbols", "binary_facts"})
NOISE_PATH_FRAGMENTS = (
    "/.git/",
    "/node_modules/",
    "/__pycache__/",
    "/.pytest_cache/",
    "/.mypy_cache/",
)

FACT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "paths": (
        re.compile(r"/[A-Za-z0-9._+@%:-]+(?:/[A-Za-z0-9._+@%:-]+)+"),
        re.compile(
            r"\b[A-Za-z0-9._+@%:-]+(?:/[A-Za-z0-9._+@%:-]+)+"
            r"\.(?:c|cc|cpp|cxx|h|hpp|hh|js|mjs|cjs|ts|tsx|py|rs|go|java|rb|sh|json|toml|yaml|yml|md)\b"
        ),
    ),
    "errors": (
        re.compile(
            r"(?im)^.*\b(?:error|failed|failure|not found|no such file|undefined|cannot|exception|traceback|"
            r"segmentation|terminated|command not found|permission denied|timed out)\b.*$"
        ),
    ),
    "symbols": (
        re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\s*\("),
        re.compile(r"<([A-Za-z_.$][A-Za-z0-9_.$@+-]{2,})>"),
    ),
    "binary_facts": (
        re.compile(r"\b(?:Entry point|LOAD|GNU_STACK|Program Headers|Section Headers|SYMTAB|STRTAB|\.text|\.data|\.bss|\.rodata)\b"),
        re.compile(r"\b0x[0-9a-fA-F]{4,}\b"),
        re.compile(r"(?m)^\s*[0-9a-fA-F]{6,}:"),
    ),
}


def analyze_output_compaction(*, mew_artifact_root: object) -> dict[str, object]:
    """Analyze raw-vs-provider-visible tool output compaction from artifacts."""

    root = Path(str(mew_artifact_root)).expanduser()
    tool_results_path = _resolve_required(root, "tool_results.jsonl")
    artifact_root = tool_results_path.parent
    provider_requests_path = _resolve_required(artifact_root, "native-provider-requests.json")
    render_outputs_path = _resolve_optional(artifact_root, "tool_render_outputs.jsonl")

    tool_results = tuple(_mapping(row) for row in _read_jsonl(tool_results_path))
    provider_outputs = _provider_outputs_by_call_id(_read_json_mapping(provider_requests_path))
    render_outputs = _render_outputs_by_call_id(_read_jsonl(render_outputs_path))

    result_reports = tuple(
        _result_report(
            index=index + 1,
            result=result,
            provider_output=str(provider_outputs.get(_provider_call_id(result)) or ""),
            render_output=_mapping(render_outputs.get(_provider_call_id(result))),
        )
        for index, result in enumerate(tool_results)
    )
    aggregate = _aggregate(result_reports)
    return {
        "schema_version": OUTPUT_COMPACTION_AUDIT_SCHEMA_VERSION,
        "report_kind": OUTPUT_COMPACTION_AUDIT_REPORT_KIND,
        "sidecar_only": True,
        "provider_visible_behavior_changed": False,
        "inputs": {
            "mew_artifact_root": str(root.resolve(strict=False)),
            "tool_results": str(tool_results_path.resolve(strict=False)),
            "native_provider_requests": str(provider_requests_path.resolve(strict=False)),
            "tool_render_outputs": str(render_outputs_path.resolve(strict=False)) if render_outputs_path else None,
        },
        "result_count": len(result_reports),
        "fact_categories": sorted(FACT_PATTERNS),
        "critical_fact_categories": sorted(CRITICAL_FACT_CATEGORIES),
        "aggregate": aggregate,
        "results": list(result_reports),
        "top_losses": _top_losses(result_reports),
        "interpretation": _interpretation(aggregate),
    }


def write_output_compaction_audit_report(
    *,
    mew_artifact_root: object,
    out_json: object,
    out_md: object,
) -> dict[str, object]:
    """Build and write JSON plus Markdown output compaction audit reports."""

    report = analyze_output_compaction(mew_artifact_root=mew_artifact_root)
    json_path = Path(str(out_json)).expanduser()
    md_path = Path(str(out_md)).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_output_compaction_markdown(report) + "\n", encoding="utf-8")
    return report


def format_output_compaction_markdown(report: Mapping[str, object]) -> str:
    """Render a compact Markdown output compaction audit report."""

    inputs = _mapping(report.get("inputs"))
    aggregate = _mapping(report.get("aggregate"))
    lines = [
        "# M6.24 Output Compaction Audit",
        "",
        "Artifact-only diagnostic. This report does not affect live mew behavior.",
        "",
        "## Inputs",
        "",
        f"- mew artifact root: `{_md(str(inputs.get('mew_artifact_root') or ''))}`",
        f"- tool results: `{_md(str(inputs.get('tool_results') or ''))}`",
        f"- native provider requests: `{_md(str(inputs.get('native_provider_requests') or ''))}`",
        f"- tool render outputs: `{_md(str(inputs.get('tool_render_outputs') or ''))}`",
        "",
        "## Summary",
        "",
        f"- Tool results: {int(report.get('result_count') or 0)}",
        f"- Results with provider output: {int(aggregate.get('results_with_provider_output') or 0)}",
        f"- Raw output chars: {int(aggregate.get('raw_output_chars_total') or 0)}",
        f"- Provider-visible output chars: {int(aggregate.get('provider_visible_output_chars_total') or 0)}",
        f"- Omitted output chars: {int(aggregate.get('omitted_output_chars_total') or 0)}",
        f"- Results with critical fact loss: {int(aggregate.get('critical_fact_loss_result_count') or 0)}",
        f"- Lost critical fact count: {int(aggregate.get('lost_critical_fact_count') or 0)}",
        "",
        "## Lost Facts By Category",
        "",
        "| Category | Lost facts |",
        "|---|---:|",
    ]
    for category, count in _sorted_counter(_mapping(aggregate.get("lost_facts_by_category"))):
        lines.append(f"| `{_md(category)}` | {count} |")
    if not aggregate.get("lost_facts_by_category"):
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## Top Losses",
            "",
            "| # | Call | Tool | Raw chars | Visible chars | Lost critical | Command | Missing samples |",
            "|---:|---|---|---:|---:|---:|---|---|",
        ]
    )
    for index, row in enumerate([item for item in report.get("top_losses") or [] if isinstance(item, Mapping)], start=1):
        samples = "; ".join(str(item) for item in row.get("missing_fact_samples") or [])
        lines.append(
            f"| {index} | `{_md(str(row.get('provider_call_id') or ''))}` | "
            f"`{_md(str(row.get('tool_name') or ''))}` | "
            f"{int(row.get('raw_output_chars') or 0)} | "
            f"{int(row.get('provider_visible_output_chars') or 0)} | "
            f"{int(row.get('lost_critical_fact_count') or 0)} | "
            f"`{_md(_clip(str(row.get('command') or ''), 80))}` | "
            f"{_md(_clip(samples, 160))} |"
        )

    lines.extend(["", "## Interpretation", ""])
    for item in report.get("interpretation") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _result_report(
    *,
    index: int,
    result: Mapping[str, object],
    provider_output: str,
    render_output: Mapping[str, object],
) -> dict[str, object]:
    payload = _first_payload(result)
    raw_output = _raw_output_text(payload)
    visible_output = provider_output
    matched_provider_output = bool(provider_output)
    raw_facts = _facts_by_category(raw_output)
    visible_facts = _facts_by_category(visible_output)
    lost_by_category = (
        {
            category: sorted(raw_facts[category] - visible_facts.get(category, set()))
            for category in sorted(raw_facts)
            if raw_facts[category] - visible_facts.get(category, set())
        }
        if matched_provider_output
        else {}
    )
    lost_critical = sum(len(values) for category, values in lost_by_category.items() if category in CRITICAL_FACT_CATEGORIES)
    raw_chars = len(raw_output)
    visible_chars = len(visible_output)
    return {
        "index": index,
        "provider_call_id": _provider_call_id(result),
        "tool_name": str(result.get("tool_name") or payload.get("tool_name") or ""),
        "command": str(payload.get("command") or ""),
        "status": str(result.get("status") or payload.get("status") or ""),
        "exit_code": payload.get("exit_code"),
        "raw_output_chars": raw_chars,
        "provider_visible_output_chars": visible_chars,
        "render_output_chars": _optional_int(render_output.get("output_chars")),
        "render_output_bytes": _optional_int(render_output.get("output_bytes")),
        "omitted_output_chars": max(raw_chars - visible_chars, 0) if matched_provider_output else 0,
        "provider_output_missing": not matched_provider_output,
        "compaction_metrics_eligible": matched_provider_output,
        "output_truncated": bool(payload.get("output_truncated")),
        "tail_only_markers": _tail_only_markers(visible_output),
        "raw_facts_by_category_count": {category: len(values) for category, values in sorted(raw_facts.items())},
        "visible_facts_by_category_count": {category: len(values) for category, values in sorted(visible_facts.items())},
        "lost_facts_by_category_count": {category: len(values) for category, values in lost_by_category.items()},
        "lost_critical_fact_count": lost_critical,
        "missing_fact_samples": _missing_fact_samples(lost_by_category),
    }


def _aggregate(reports: Sequence[Mapping[str, object]]) -> dict[str, object]:
    lost_by_category: Counter[str] = Counter()
    raw_by_category: Counter[str] = Counter()
    visible_by_category: Counter[str] = Counter()
    for report in reports:
        lost_by_category.update({str(key): int(value) for key, value in _mapping(report.get("lost_facts_by_category_count")).items()})
        raw_by_category.update({str(key): int(value) for key, value in _mapping(report.get("raw_facts_by_category_count")).items()})
        visible_by_category.update({str(key): int(value) for key, value in _mapping(report.get("visible_facts_by_category_count")).items()})
    lost_critical = sum(count for category, count in lost_by_category.items() if category in CRITICAL_FACT_CATEGORIES)
    return {
        "result_count": len(reports),
        "results_with_provider_output": sum(1 for report in reports if not report.get("provider_output_missing")),
        "provider_output_missing_count": sum(1 for report in reports if report.get("provider_output_missing")),
        "raw_output_chars_total": sum(int(report.get("raw_output_chars") or 0) for report in reports),
        "provider_visible_output_chars_total": sum(int(report.get("provider_visible_output_chars") or 0) for report in reports),
        "omitted_output_chars_total": sum(int(report.get("omitted_output_chars") or 0) for report in reports),
        "output_truncated_result_count": sum(1 for report in reports if report.get("output_truncated")),
        "tail_only_marker_result_count": sum(1 for report in reports if report.get("tail_only_markers")),
        "lost_facts_by_category": dict(sorted(lost_by_category.items())),
        "raw_facts_by_category": dict(sorted(raw_by_category.items())),
        "visible_facts_by_category": dict(sorted(visible_by_category.items())),
        "lost_critical_fact_count": lost_critical,
        "critical_fact_loss_result_count": sum(1 for report in reports if int(report.get("lost_critical_fact_count") or 0) > 0),
    }


def _interpretation(aggregate: Mapping[str, object]) -> list[str]:
    notes: list[str] = []
    result_count = int(aggregate.get("result_count") or 0)
    if result_count == 0:
        return ["No tool results were found; H5 cannot be evaluated from this artifact."]
    if int(aggregate.get("provider_output_missing_count") or 0):
        notes.append("Some tool results have no matching provider-visible function_call_output in saved requests.")
    if int(aggregate.get("critical_fact_loss_result_count") or 0):
        notes.append(
            "H5 found a concrete output-visibility gap: raw tool output contains critical facts missing from provider-visible output."
        )
    else:
        notes.append("H5 found no critical raw-vs-visible fact loss in the saved tool outputs.")
    if int(aggregate.get("tail_only_marker_result_count") or 0):
        notes.append("Some provider-visible outputs look tail-only or visibly compacted.")
    notes.append("This diagnostic is evidence for targeted output visibility changes only; it does not authorize broad rendering changes.")
    return notes


def _top_losses(reports: Sequence[Mapping[str, object]], *, limit: int = 12) -> list[dict[str, object]]:
    ranked = sorted(
        (dict(report) for report in reports),
        key=lambda row: (
            -int(row.get("lost_critical_fact_count") or 0),
            -int(row.get("omitted_output_chars") or 0),
            int(row.get("index") or 0),
        ),
    )
    return [
        {
            "provider_call_id": row.get("provider_call_id"),
            "tool_name": row.get("tool_name"),
            "command": row.get("command"),
            "raw_output_chars": row.get("raw_output_chars"),
            "provider_visible_output_chars": row.get("provider_visible_output_chars"),
            "omitted_output_chars": row.get("omitted_output_chars"),
            "lost_critical_fact_count": row.get("lost_critical_fact_count"),
            "lost_facts_by_category_count": row.get("lost_facts_by_category_count"),
            "missing_fact_samples": row.get("missing_fact_samples"),
        }
        for row in ranked[:limit]
    ]


def _provider_outputs_by_call_id(native_requests: Mapping[str, object]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for request in _sequence(native_requests.get("requests")):
        request_mapping = _mapping(request)
        body = _mapping(request_mapping.get("request_body"))
        for item in _sequence(body.get("input")):
            item_mapping = _mapping(item)
            if item_mapping.get("type") == "function_call_output":
                call_id = str(item_mapping.get("call_id") or "")
                if call_id:
                    outputs[call_id] = str(item_mapping.get("output") or "")
    return outputs


def _render_outputs_by_call_id(rows: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    outputs: dict[str, Mapping[str, object]] = {}
    for row in rows:
        call_id = str(row.get("call_id") or "")
        if call_id:
            outputs[call_id] = row
    return outputs


def _provider_call_id(result: Mapping[str, object]) -> str:
    payload = _first_payload(result)
    return str(result.get("provider_call_id") or payload.get("provider_call_id") or "")


def _first_payload(result: Mapping[str, object]) -> Mapping[str, object]:
    content = result.get("content")
    if isinstance(content, list) and content and isinstance(content[0], Mapping):
        return content[0]
    return {}


def _raw_output_text(payload: Mapping[str, object]) -> str:
    parts = [
        str(payload.get("stdout") or ""),
        str(payload.get("stderr") or ""),
    ]
    return "\n".join(part for part in parts if part)


def _facts_by_category(text: str) -> dict[str, set[str]]:
    facts: dict[str, set[str]] = {}
    for category, patterns in FACT_PATTERNS.items():
        values: set[str] = set()
        for pattern in patterns:
            for match in pattern.finditer(text):
                value = match.group(1) if match.lastindex else match.group(0)
                value = value.strip()
                if category == "paths" and _is_noise_path(value):
                    continue
                if len(value) >= 3:
                    values.add(_normalize_fact(value))
        if values:
            facts[category] = values
    return facts


def _normalize_fact(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _is_noise_path(value: str) -> bool:
    normalized = value if value.startswith("/") else f"/{value}"
    return any(fragment in normalized for fragment in NOISE_PATH_FRAGMENTS)


def _tail_only_markers(text: str) -> tuple[str, ...]:
    markers: list[str] = []
    if "output_tail:" in text:
        markers.append("output_tail")
    if "\n...\n" in text or "\t\t..." in text:
        markers.append("ellipsis")
    return tuple(markers)


def _missing_fact_samples(lost_by_category: Mapping[str, Sequence[str]], *, limit: int = 8) -> list[str]:
    samples: list[str] = []
    for category in sorted(CRITICAL_FACT_CATEGORIES):
        for value in lost_by_category.get(category, ())[:limit]:
            samples.append(f"{category}:{value}")
            if len(samples) >= limit:
                return samples
    return samples


def _resolve_required(root: Path, name: str) -> Path:
    resolved = _resolve_optional(root, name)
    if resolved is None:
        raise FileNotFoundError(f"{name} not found under {root}")
    return resolved


def _resolve_optional(root: Path, name: str) -> Path | None:
    if root.is_file():
        if root.name == name:
            return root
        root = root.parent
    candidate = root / name
    if candidate.is_file():
        return candidate
    matches = sorted(root.rglob(name))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous {name} under {root}: {len(matches)} matches")
    return None


def _read_json_mapping(path: Path) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError(f"expected JSON object in {path}")
    return raw


def _read_jsonl(path: Path | None) -> tuple[Mapping[str, object], ...]:
    if path is None or not path.is_file():
        return ()
    rows: list[Mapping[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL in {path}:{line_number}: {exc}") from exc
        rows.append(_mapping(raw))
    return tuple(rows)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> tuple[object, ...]:
    return tuple(value) if isinstance(value, list | tuple) else ()


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sorted_counter(counter: Mapping[str, object]) -> list[tuple[str, int]]:
    return sorted(((str(key), int(value)) for key, value in counter.items()), key=lambda item: (-item[1], item[0]))


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."
