"""Artifact-only provider response-continuity diagnostics for M6.24.

The audit reads saved native provider request and transcript artifacts. It
does not call a model and does not change live loop behavior.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

PROVIDER_CONTINUITY_AUDIT_SCHEMA_VERSION = 1
PROVIDER_CONTINUITY_AUDIT_REPORT_KIND = "m6_24_provider_continuity_audit"


def analyze_provider_continuity(*, mew_artifact_root: object) -> dict[str, object]:
    """Analyze provider-side response continuity from saved artifacts."""

    root = Path(str(mew_artifact_root)).expanduser()
    provider_requests_path = _resolve_provider_requests_path(root)
    artifact_root = provider_requests_path.parent
    transcript_path = _resolve_required(artifact_root, "response_transcript.json")
    response_items_path = _resolve_optional(artifact_root, "response_items.jsonl")
    inventory_path = _resolve_optional(artifact_root, "provider-request-inventory.json")

    provider_raw = _read_json_mapping(provider_requests_path)
    requests = tuple(_mapping(item) for item in _sequence(provider_raw.get("requests")))
    transcript = _read_json_mapping(transcript_path)
    transcript_items = tuple(_mapping(item) for item in _sequence(transcript.get("items")))
    response_items = _read_jsonl(response_items_path) if response_items_path else ()
    transcript_summary = _transcript_summary(transcript_items)
    turn_reports = tuple(
        _turn_report(
            index=index + 1,
            request=request,
            transcript_summary=transcript_summary,
        )
        for index, request in enumerate(requests)
    )
    aggregate = _aggregate(turn_reports, transcript_summary, response_items)
    return {
        "schema_version": PROVIDER_CONTINUITY_AUDIT_SCHEMA_VERSION,
        "report_kind": PROVIDER_CONTINUITY_AUDIT_REPORT_KIND,
        "sidecar_only": True,
        "provider_visible_behavior_changed": False,
        "inputs": {
            "mew_artifact_root": str(root.resolve(strict=False)),
            "native_provider_requests": str(provider_requests_path.resolve(strict=False)),
            "provider_request_inventory": str(inventory_path.resolve(strict=False)) if inventory_path else None,
            "response_transcript": str(transcript_path.resolve(strict=False)),
            "response_items_jsonl": str(response_items_path.resolve(strict=False)) if response_items_path else None,
        },
        "request_count": len(requests),
        "transcript_item_count": len(transcript_items),
        "response_items_jsonl_count": len(response_items),
        "transcript": transcript_summary,
        "aggregate": aggregate,
        "turns": list(turn_reports),
        "interpretation": _interpretation(aggregate),
    }


def write_provider_continuity_audit_report(
    *,
    mew_artifact_root: object,
    out_json: object,
    out_md: object,
) -> dict[str, object]:
    """Build and write JSON plus Markdown continuity audit reports."""

    report = analyze_provider_continuity(mew_artifact_root=mew_artifact_root)
    json_path = Path(str(out_json)).expanduser()
    md_path = Path(str(out_md)).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_provider_continuity_markdown(report) + "\n", encoding="utf-8")
    return report


def format_provider_continuity_markdown(report: Mapping[str, object]) -> str:
    """Render a compact Markdown continuity audit report."""

    inputs = _mapping(report.get("inputs"))
    aggregate = _mapping(report.get("aggregate"))
    transcript = _mapping(report.get("transcript"))
    lines = [
        "# M6.24 Provider Continuity Audit",
        "",
        "Artifact-only diagnostic. This report does not affect live mew behavior.",
        "",
        "## Inputs",
        "",
        f"- mew artifact root: `{_md(str(inputs.get('mew_artifact_root') or ''))}`",
        f"- native provider requests: `{_md(str(inputs.get('native_provider_requests') or ''))}`",
        f"- provider request inventory: `{_md(str(inputs.get('provider_request_inventory') or ''))}`",
        f"- response transcript: `{_md(str(inputs.get('response_transcript') or ''))}`",
        f"- response items jsonl: `{_md(str(inputs.get('response_items_jsonl') or ''))}`",
        "",
        "## Summary",
        "",
        f"- Requests: {int(report.get('request_count') or 0)}",
        f"- Transcript items: {int(report.get('transcript_item_count') or 0)}",
        f"- Response items jsonl: {int(report.get('response_items_jsonl_count') or 0)}",
        f"- Requests after first: {int(aggregate.get('requests_after_first') or 0)}",
        f"- Previous response present in wire body after first: {int(aggregate.get('previous_response_present_after_first') or 0)}",
        f"- Previous response missing after first: {int(aggregate.get('previous_response_missing_after_first') or 0)}",
        f"- Expected previous response mismatches: {int(aggregate.get('expected_previous_response_mismatch_count') or 0)}",
        f"- Delta coverage mismatches: {int(aggregate.get('delta_coverage_mismatch_count') or 0)}",
        f"- Wire count metadata mismatches: {int(aggregate.get('wire_count_metadata_mismatch_count') or 0)}",
        f"- Pairing error count: {int(aggregate.get('pairing_error_count') or 0)}",
        "",
        "## Delta Modes",
        "",
        "| Mode | Count |",
        "|---|---:|",
    ]
    for key, value in _sorted_counter(_mapping(aggregate.get("delta_mode_counts"))):
        lines.append(f"| `{_md(key)}` | {value} |")
    if not aggregate.get("delta_mode_counts"):
        lines.append("| none | 0 |")

    lines.extend(
        [
            "",
            "## Transcript Summary",
            "",
            f"- Response turns: {int(transcript.get('response_turn_count') or 0)}",
            f"- Reasoning items: {int(transcript.get('reasoning_count') or 0)}",
            f"- Call count: {int(transcript.get('call_count') or 0)}",
            f"- Output count: {int(transcript.get('output_count') or 0)}",
            f"- Non-tool count: {int(transcript.get('non_tool_count') or 0)}",
            "",
            "## First Ten Requests",
            "",
            "| Turn | Prev in body | Delta mode | Expected prev match | Delta covers logical | Prefix | Wire items | Reasoning refs |",
            "|---:|---|---|---|---|---:|---:|---:|",
        ]
    )
    for row in [item for item in report.get("turns") or [] if isinstance(item, Mapping)][:10]:
        lines.append(
            f"| {int(row.get('turn_index') or 0)} | "
            f"{_bool(row.get('previous_response_id_in_request_body'))} | "
            f"`{_md(str(row.get('previous_response_delta_mode') or 'none'))}` | "
            f"{_bool(row.get('expected_previous_response_match'))} | "
            f"{_bool(row.get('delta_covers_logical_input'))} | "
            f"{_int_or_blank(row.get('previous_response_prefix_item_count'))} | "
            f"{_int_or_blank(row.get('wire_input_item_count'))} | "
            f"{int(row.get('reasoning_sidecar_refs_used_count') or 0)} |"
        )

    warnings = [str(item) for item in aggregate.get("warnings") or []]
    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{_md(warning)}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Interpretation", ""])
    for item in report.get("interpretation") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


def _turn_report(
    *,
    index: int,
    request: Mapping[str, object],
    transcript_summary: Mapping[str, object],
) -> dict[str, object]:
    turn_index = int(request.get("turn_index") or index)
    previous_response_id = str(request.get("previous_response_id") or "")
    body = _mapping(request.get("request_body"))
    body_previous_response_id = str(body.get("previous_response_id") or "")
    effective_previous_response_id = body_previous_response_id
    expected_previous_response_id = _expected_previous_response_id(transcript_summary, turn_index)
    expected_match = (
        None
        if turn_index <= 1 or not expected_previous_response_id
        else effective_previous_response_id == expected_previous_response_id
    )
    wire_items = _sequence(body.get("input"))
    logical_items = _mapping_tuple(request.get("logical_input_items"))
    descriptor_logical_count = _optional_int(request.get("logical_input_item_count"))
    logical_count = len(logical_items) if logical_items else descriptor_logical_count
    prefix_count = _optional_int(request.get("previous_response_prefix_item_count"))
    leading_refresh_count = _optional_int(request.get("previous_response_leading_refresh_item_count")) or 0
    descriptor_wire_count = _optional_int(request.get("wire_input_item_count"))
    actual_wire_count = len(wire_items)
    delta_covers_logical_input = (
        None
        if turn_index <= 1 or logical_count is None or prefix_count is None
        else prefix_count + actual_wire_count - leading_refresh_count == logical_count
    )
    logical_count_descriptor_match = None if descriptor_logical_count is None or not logical_items else descriptor_logical_count == len(logical_items)
    wire_matches_logical_delta = _wire_matches_logical_delta(
        logical_items=logical_items,
        wire_items=wire_items,
        prefix_count=prefix_count,
        leading_refresh_count=leading_refresh_count,
        turn_index=turn_index,
    )
    return {
        "turn_index": turn_index,
        "descriptor_previous_response_id": previous_response_id,
        "previous_response_id": effective_previous_response_id,
        "previous_response_id_in_request_body": bool(effective_previous_response_id),
        "descriptor_previous_response_id_in_request_body": bool(request.get("previous_response_id_in_request_body")),
        "request_body_previous_response_id": body_previous_response_id,
        "previous_response_body_descriptor_consistent": previous_response_id == body_previous_response_id
        and bool(request.get("previous_response_id_in_request_body")) == bool(body_previous_response_id),
        "expected_previous_response_id": expected_previous_response_id,
        "expected_previous_response_match": expected_match,
        "previous_response_delta_mode": str(request.get("previous_response_delta_mode") or "none"),
        "logical_input_item_count": logical_count,
        "descriptor_logical_input_item_count": descriptor_logical_count,
        "logical_input_count_descriptor_match": logical_count_descriptor_match,
        "logical_input_items_available": bool(logical_items),
        "previous_response_prefix_item_count": prefix_count,
        "delta_covers_logical_input": delta_covers_logical_input,
        "wire_matches_logical_delta": wire_matches_logical_delta,
        "wire_input_item_count": actual_wire_count,
        "descriptor_wire_input_item_count": descriptor_wire_count,
        "wire_input_count_descriptor_match": None if descriptor_wire_count is None else descriptor_wire_count == actual_wire_count,
        "body_input_item_count": len(wire_items),
        "descriptor_input_item_count": _optional_int(request.get("input_item_count")),
        "reasoning_sidecar_refs_used_count": len(_sequence(request.get("reasoning_sidecar_refs_used"))),
        "suppressed_context_refresh_item_count": len(_sequence(request.get("suppressed_context_refresh_items"))),
        "previous_response_leading_refresh_item_count": leading_refresh_count,
        "previous_response_suppressed_context_refresh_item_count": _optional_int(
            request.get("previous_response_suppressed_context_refresh_item_count")
        ),
    }


def _transcript_summary(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_turn: dict[int, list[Mapping[str, object]]] = defaultdict(list)
    response_ids_by_turn: dict[int, list[str]] = defaultdict(list)
    sequence_errors: list[str] = []
    pairing_errors: list[str] = []
    calls: dict[str, Mapping[str, object]] = {}
    outputs: dict[str, Mapping[str, object]] = {}
    call_item_count = 0
    output_item_count = 0
    last_sequence = 0

    for item in items:
        sequence = int(item.get("sequence") or 0)
        if sequence <= last_sequence:
            sequence_errors.append(f"non_monotonic_sequence:{last_sequence}->{sequence}")
        last_sequence = sequence
        turn = _turn_index(str(item.get("turn_id") or ""))
        if turn is not None:
            by_turn[turn].append(item)
        response_id = str(item.get("response_id") or "")
        if turn is not None and response_id and response_id not in response_ids_by_turn[turn]:
            response_ids_by_turn[turn].append(response_id)
        kind = str(item.get("kind") or "")
        call_id = str(item.get("call_id") or "")
        if kind in {"function_call", "custom_tool_call", "finish_call"}:
            call_item_count += 1
            if not call_id:
                pairing_errors.append(f"call_missing_call_id:{sequence}:{kind}")
                continue
            if call_id in calls:
                sequence_errors.append(f"duplicate_call_id:{call_id}")
            calls[call_id] = item
        if kind in {"function_call_output", "custom_tool_call_output", "finish_output"}:
            output_item_count += 1
            if not call_id:
                pairing_errors.append(f"output_missing_call_id:{sequence}:{kind}")
                continue
            if call_id in outputs:
                sequence_errors.append(f"duplicate_output_for_call_id:{call_id}")
            outputs[call_id] = item

    for call_id in calls:
        call = calls[call_id]
        output = outputs.get(call_id)
        if output is None:
            pairing_errors.append(f"missing_output_for_call_id:{call_id}")
            continue
        if not _call_output_kind_matches(str(call.get("kind") or ""), str(output.get("kind") or "")):
            pairing_errors.append(f"call_output_kind_mismatch:{call_id}:{call.get('kind')}:{output.get('kind')}")
        call_tool = str(call.get("tool_name") or "")
        output_tool = str(output.get("tool_name") or "")
        if call_tool and output_tool and call_tool != output_tool:
            pairing_errors.append(f"tool_name_mismatch:{call_id}:{call_tool}:{output_tool}")
        if int(output.get("sequence") or 0) < int(call.get("sequence") or 0):
            pairing_errors.append(f"output_before_call:{call_id}")
    for call_id in outputs:
        if call_id not in calls:
            pairing_errors.append(f"orphan_output_for_call_id:{call_id}")

    cumulative_by_turn: dict[str, int] = {}
    running = 0
    for turn in sorted(by_turn):
        running += len(by_turn[turn])
        cumulative_by_turn[str(turn)] = running

    kind_counts = Counter(str(item.get("kind") or "unknown") for item in items)
    return {
        "item_count": len(items),
        "response_turn_count": len(by_turn),
        "response_ids_by_turn": {str(turn): ids for turn, ids in sorted(response_ids_by_turn.items())},
        "cumulative_item_count_by_turn": cumulative_by_turn,
        "items_by_kind": dict(sorted(kind_counts.items())),
        "reasoning_count": kind_counts.get("reasoning", 0),
        "call_count": call_item_count,
        "output_count": output_item_count,
        "unique_call_id_count": len(calls),
        "unique_output_call_id_count": len(outputs),
        "non_tool_count": sum(kind_counts.get(kind, 0) for kind in ("input_message", "assistant_message", "reasoning")),
        "pairing_error_count": len(pairing_errors),
        "pairing_errors": pairing_errors[:20],
        "sequence_error_count": len(sequence_errors),
        "sequence_errors": sequence_errors[:20],
    }


def _aggregate(
    reports: Sequence[Mapping[str, object]],
    transcript_summary: Mapping[str, object],
    response_items: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    after_first = [row for row in reports if int(row.get("turn_index") or 0) > 1]
    delta_modes = Counter(str(row.get("previous_response_delta_mode") or "none") for row in reports)
    warnings: list[str] = []
    missing_previous = [row for row in after_first if not row.get("previous_response_id_in_request_body")]
    previous_mismatches = [row for row in after_first if row.get("expected_previous_response_match") is False]
    delta_coverage_mismatches = [row for row in after_first if row.get("delta_covers_logical_input") is False]
    wire_logical_mismatches = [row for row in after_first if row.get("wire_matches_logical_delta") is False]
    wire_logical_unknown = [row for row in after_first if row.get("wire_matches_logical_delta") is None]
    logical_count_mismatches = [row for row in reports if row.get("logical_input_count_descriptor_match") is False]
    unknown_previous = [row for row in after_first if row.get("expected_previous_response_match") is None]
    unknown_delta_coverage = [row for row in after_first if row.get("delta_covers_logical_input") is None]
    wire_count_mismatches = [row for row in reports if row.get("wire_input_count_descriptor_match") is False]
    body_descriptor_mismatches = [row for row in reports if row.get("previous_response_body_descriptor_consistent") is False]
    no_reasoning_refs = sum(1 for row in reports if int(row.get("reasoning_sidecar_refs_used_count") or 0) == 0)

    if missing_previous:
        warnings.append(f"missing_previous_response_after_first:{len(missing_previous)}")
    if previous_mismatches:
        warnings.append(f"expected_previous_response_mismatch:{len(previous_mismatches)}")
    if delta_coverage_mismatches:
        warnings.append(f"delta_coverage_mismatch:{len(delta_coverage_mismatches)}")
    if wire_logical_mismatches:
        warnings.append(f"wire_logical_delta_mismatch:{len(wire_logical_mismatches)}")
    if wire_logical_unknown:
        warnings.append(f"wire_logical_delta_unknown:{len(wire_logical_unknown)}")
    if logical_count_mismatches:
        warnings.append(f"logical_count_metadata_mismatch:{len(logical_count_mismatches)}")
    if unknown_previous:
        warnings.append(f"previous_response_unknown:{len(unknown_previous)}")
    if unknown_delta_coverage:
        warnings.append(f"delta_coverage_unknown:{len(unknown_delta_coverage)}")
    if wire_count_mismatches:
        warnings.append(f"wire_count_metadata_mismatch:{len(wire_count_mismatches)}")
    if body_descriptor_mismatches:
        warnings.append(f"previous_response_body_descriptor_mismatch:{len(body_descriptor_mismatches)}")
    if no_reasoning_refs == len(reports) and reports:
        warnings.append("reasoning_items_carried_only_by_provider_continuity")
    if int(transcript_summary.get("pairing_error_count") or 0):
        warnings.append(f"pairing_errors:{int(transcript_summary.get('pairing_error_count') or 0)}")
    if int(transcript_summary.get("sequence_error_count") or 0):
        warnings.append(f"sequence_errors:{int(transcript_summary.get('sequence_error_count') or 0)}")
    if response_items and len(response_items) != int(transcript_summary.get("item_count") or 0):
        warnings.append("response_items_jsonl_count_differs_from_response_transcript")

    return {
        "requests_after_first": len(after_first),
        "previous_response_present_after_first": sum(1 for row in after_first if row.get("previous_response_id_in_request_body")),
        "previous_response_missing_after_first": len(missing_previous),
        "expected_previous_response_match_count": sum(1 for row in after_first if row.get("expected_previous_response_match") is True),
        "expected_previous_response_mismatch_count": len(previous_mismatches),
        "expected_previous_response_unknown_count": len(unknown_previous),
        "delta_coverage_match_count": sum(1 for row in after_first if row.get("delta_covers_logical_input") is True),
        "delta_coverage_mismatch_count": len(delta_coverage_mismatches),
        "delta_coverage_unknown_count": len(unknown_delta_coverage),
        "wire_logical_delta_match_count": sum(1 for row in after_first if row.get("wire_matches_logical_delta") is True),
        "wire_logical_delta_mismatch_count": len(wire_logical_mismatches),
        "wire_logical_delta_unknown_count": len(wire_logical_unknown),
        "logical_count_metadata_mismatch_count": len(logical_count_mismatches),
        "wire_count_metadata_mismatch_count": len(wire_count_mismatches),
        "previous_response_body_descriptor_mismatch_count": len(body_descriptor_mismatches),
        "delta_mode_counts": dict(sorted(delta_modes.items())),
        "max_wire_input_item_count": max((int(row.get("wire_input_item_count") or 0) for row in reports), default=0),
        "max_logical_input_item_count": max((int(row.get("logical_input_item_count") or 0) for row in reports), default=0),
        "max_previous_response_prefix_item_count": max(
            (int(row.get("previous_response_prefix_item_count") or 0) for row in reports),
            default=0,
        ),
        "requests_with_reasoning_sidecar_refs_used": sum(
            1 for row in reports if int(row.get("reasoning_sidecar_refs_used_count") or 0) > 0
        ),
        "requests_with_zero_reasoning_sidecar_refs_used": no_reasoning_refs,
        "response_items_jsonl_matches_transcript_count": bool(
            response_items and len(response_items) == int(transcript_summary.get("item_count") or 0)
        ),
        "pairing_error_count": int(transcript_summary.get("pairing_error_count") or 0),
        "sequence_error_count": int(transcript_summary.get("sequence_error_count") or 0),
        "warnings": warnings,
    }


def _interpretation(aggregate: Mapping[str, object]) -> list[str]:
    notes: list[str] = []
    if int(aggregate.get("requests_after_first") or 0) > 0 and int(aggregate.get("previous_response_missing_after_first") or 0) == 0:
        notes.append("Every request after the first used previous_response_id.")
    if int(aggregate.get("expected_previous_response_mismatch_count") or 0) == 0 and int(
        aggregate.get("expected_previous_response_unknown_count") or 0
    ) == 0:
        notes.append("Every auditable previous_response_id matches the previous turn's recorded response_id.")
    if int(aggregate.get("delta_coverage_mismatch_count") or 0) == 0 and int(aggregate.get("delta_coverage_unknown_count") or 0) == 0:
        notes.append("Delta prefix and wire item counts cover the recorded logical input for auditable turns.")
    if int(aggregate.get("wire_logical_delta_mismatch_count") or 0) == 0 and int(
        aggregate.get("wire_logical_delta_unknown_count") or 0
    ) == 0:
        notes.append("Wire input items match the saved logical input delta for auditable turns.")
    if int(aggregate.get("requests_with_reasoning_sidecar_refs_used") or 0) == 0:
        notes.append(
            "Reasoning items are not locally replayed in the wire input; this depends on provider-side response continuity."
        )
    if int(aggregate.get("pairing_error_count") or 0) == 0 and int(aggregate.get("sequence_error_count") or 0) == 0:
        notes.append("Native call/output pairing is valid in the saved transcript.")
    if _has_critical_gap(aggregate):
        notes.append("H3 found a concrete continuity gap worth fixing before further behavior experiments.")
    else:
        notes.append(
            "H3 does not by itself justify changing continuity behavior; use this as evidence before considering full local replay."
        )
    return notes


def _has_critical_gap(aggregate: Mapping[str, object]) -> bool:
    critical_keys = (
        "expected_previous_response_mismatch_count",
        "expected_previous_response_unknown_count",
        "delta_coverage_mismatch_count",
        "delta_coverage_unknown_count",
        "wire_logical_delta_mismatch_count",
        "wire_logical_delta_unknown_count",
        "logical_count_metadata_mismatch_count",
        "wire_count_metadata_mismatch_count",
        "previous_response_body_descriptor_mismatch_count",
        "pairing_error_count",
        "sequence_error_count",
    )
    if any(int(aggregate.get(key) or 0) for key in critical_keys):
        return True
    if not aggregate.get("response_items_jsonl_matches_transcript_count"):
        return True
    return False


def _resolve_provider_requests_path(root: Path) -> Path:
    if root.is_file():
        if root.name != "native-provider-requests.json":
            raise ValueError(f"expected native-provider-requests.json, got {root}")
        return root
    candidate = root / "native-provider-requests.json"
    if candidate.is_file():
        return candidate
    matches = sorted(root.rglob("native-provider-requests.json"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"ambiguous native-provider-requests.json under {root}: {len(matches)} matches")
    raise FileNotFoundError(f"native-provider-requests.json not found under {root}")


def _resolve_required(root: Path, name: str) -> Path:
    resolved = _resolve_optional(root, name)
    if resolved is None:
        raise FileNotFoundError(f"{name} not found under {root}")
    return resolved


def _resolve_optional(root: Path, name: str) -> Path | None:
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


def _expected_previous_response_id(summary: Mapping[str, object], turn_index: int) -> str:
    if turn_index <= 1:
        return ""
    ids_by_turn = _mapping(summary.get("response_ids_by_turn"))
    previous_ids = _sequence(ids_by_turn.get(str(turn_index - 1)))
    return str(previous_ids[-1]) if previous_ids else ""


def _turn_index(turn_id: str) -> int | None:
    match = re.fullmatch(r"turn-(\d+)", turn_id)
    if not match:
        return None
    return int(match.group(1))


def _call_output_kind_matches(call_kind: str, output_kind: str) -> bool:
    return (
        (call_kind == "function_call" and output_kind == "function_call_output")
        or (call_kind == "custom_tool_call" and output_kind == "custom_tool_call_output")
        or (call_kind == "finish_call" and output_kind == "finish_output")
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_tuple(value: object) -> tuple[Mapping[str, object], ...]:
    return tuple(item for item in _sequence(value) if isinstance(item, Mapping))


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


def _bool(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _int_or_blank(value: object) -> str:
    parsed = _optional_int(value)
    return "" if parsed is None else str(parsed)


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _wire_matches_logical_delta(
    *,
    logical_items: Sequence[Mapping[str, object]],
    wire_items: Sequence[object],
    prefix_count: int | None,
    leading_refresh_count: int,
    turn_index: int,
) -> bool | None:
    if turn_index <= 1:
        return None
    if prefix_count is None or not logical_items:
        return None
    wire_mappings = tuple(item for item in wire_items if isinstance(item, Mapping))
    if len(wire_mappings) != len(wire_items):
        return False
    expected = tuple(logical_items[:leading_refresh_count]) + tuple(logical_items[prefix_count:])
    return _canonical_items(wire_mappings) == _canonical_items(expected)


def _canonical_items(items: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    return tuple(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in items)
