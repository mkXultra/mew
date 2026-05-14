"""Profile-aware A/B report for implement_v2 tool surfaces.

This module is deliberately artifact-only. It compares two completed native
implement_v2 artifact roots without running Harbor or calling a model.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any

from .native_tool_harness import _native_call_is_verifier
from .native_transcript import (
    CALL_ITEM_KINDS,
    OUTPUT_ITEM_KINDS,
    NativeTranscript,
    NativeTranscriptItem,
    native_transcript_hash,
    validate_native_transcript_pairing,
)
from .tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID

TOOL_SURFACE_AB_REPORT_SCHEMA_VERSION = 1
WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "apply_patch"})
COMMAND_TOOL_NAMES = frozenset({"run_command", "run_tests", "exec_command", "write_stdin", "poll_command"})
READ_PROBE_TOOL_NAMES = frozenset(
    {
        "read_file",
        "search_text",
        "glob",
        "inspect_dir",
        "list_dir",
        "run_command",
        "exec_command",
    }
)
READ_LIST_ALIAS_TOOL_NAMES = frozenset({"read_file", "search_text", "glob", "inspect_dir", "list_dir"})
FORBIDDEN_HOT_PATH_STEERING_MARKERS = (
    "first_write_due",
    "prewrite_probe_plateau",
    "required_next",
    "next_action",
    "workframe_projection",
    "workframe",
    "frontier_state_update",
)
REQUIRED_SIDECAR_ARTIFACTS = (
    "response_transcript.json",
    "proof-manifest.json",
    "provider-request-inventory.json",
    "tool_routes.jsonl",
    "tool_render_outputs.jsonl",
    "tool_result_index.json",
    "evidence_sidecar.json",
    "evidence_ref_index.json",
    "native-evidence-observation.json",
)


def build_tool_surface_ab_report(
    *,
    baseline_artifact_root: object,
    candidate_artifact_root: object,
    ab_pair_id: str,
    workspace_snapshot_id: str = "",
    task_contract_hash: str = "",
    model: str = "",
    effort: str = "",
    budget_profile: str = "",
    provider_seed: str = "",
    provider_seed_supported: bool = False,
    baseline_tags: Mapping[str, object] | None = None,
    candidate_tags: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a paired report for one legacy/candidate tool-surface run."""

    baseline = build_tool_surface_run_report(
        baseline_artifact_root,
        ab_pair_id=ab_pair_id,
        ab_role="baseline",
        default_tags={
            "workspace_snapshot_id": workspace_snapshot_id,
            "task_contract_hash": task_contract_hash,
            "model": model,
            "effort": effort,
            "budget_profile": budget_profile,
            "provider_seed": provider_seed,
            "provider_seed_supported": provider_seed_supported,
        },
        tags=baseline_tags,
    )
    candidate = build_tool_surface_run_report(
        candidate_artifact_root,
        ab_pair_id=ab_pair_id,
        ab_role="candidate",
        default_tags={
            "workspace_snapshot_id": workspace_snapshot_id,
            "task_contract_hash": task_contract_hash,
            "model": model,
            "effort": effort,
            "budget_profile": budget_profile,
            "provider_seed": provider_seed,
            "provider_seed_supported": provider_seed_supported,
        },
        tags=candidate_tags,
    )
    rows = (baseline, candidate)
    exclusion_reasons = _ab_exclusion_reasons(rows)
    ab_comparable = not exclusion_reasons
    return {
        "schema_version": TOOL_SURFACE_AB_REPORT_SCHEMA_VERSION,
        "report_kind": "tool_surface_profile_ab_report",
        "ab_pair_id": ab_pair_id,
        "ab_comparable": ab_comparable,
        "default_switch_evidence_included": ab_comparable,
        "exclusion_reasons": exclusion_reasons,
        "profiles": [row.get("profile_id") for row in rows],
        "rows": list(rows),
        "comparison": _comparison_summary(rows, ab_comparable=ab_comparable, exclusion_reasons=exclusion_reasons),
    }


def build_tool_surface_run_report(
    artifact_root: object,
    *,
    ab_pair_id: str,
    ab_role: str,
    default_tags: Mapping[str, object] | None = None,
    tags: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Summarize one native implement_v2 artifact root as an A/B row."""

    root = Path(str(artifact_root)).expanduser().resolve(strict=False)
    merged_tags = {**dict(default_tags or {}), **dict(tags or {})}
    transcript = _load_native_transcript(root / "response_transcript.json")
    validation = validate_native_transcript_pairing(transcript)
    manifest = _load_json_mapping(root / "proof-manifest.json")
    provider_requests = _load_json_mapping(root / "native-provider-requests.json")
    inventory_payload = _load_json_mapping(root / "provider-request-inventory.json")
    inventory_records = _mapping_rows(inventory_payload.get("provider_request_inventory"))
    tool_surface = _first_tool_surface(inventory_records)
    render_rows = _jsonl_rows(root / "tool_render_outputs.jsonl")
    route_rows = _jsonl_rows(root / "tool_routes.jsonl")
    evidence_observation = _load_json_mapping(root / "native-evidence-observation.json")
    calls = tuple(item for item in transcript.items if item.kind in CALL_ITEM_KINDS)
    outputs = tuple(item for item in transcript.items if item.kind in OUTPUT_ITEM_KINDS)
    first_write = _first_call(calls, WRITE_TOOL_NAMES)
    first_verifier = _first_verifier_call(calls)
    first_write_sequence = first_write.sequence if first_write is not None else None
    before_first_write = tuple(call for call in calls if first_write_sequence is None or call.sequence < first_write_sequence)
    failure_to_edit_latency = _failed_verifier_to_next_edit_latency(calls, outputs)
    render_metrics = _render_metrics(render_rows)
    provider_inventory_forbidden_ok = _provider_inventory_forbidden_ok(inventory_records)
    hidden_steering = _hidden_steering_markers(inventory_records)
    profile_id = str(tool_surface.get("profile_id") or "")
    status = str(provider_requests.get("status") or manifest.get("status") or "")
    sidecars = _sidecar_status(root)
    evidence_summary = _mapping(evidence_observation.get("summary"))
    verifier_evidence_preserved = _verifier_evidence_preserved(
        calls,
        outputs,
        evidence_summary=evidence_summary,
        evidence_observation_present=(root / "native-evidence-observation.json").is_file(),
    )
    row = {
        "schema_version": TOOL_SURFACE_AB_REPORT_SCHEMA_VERSION,
        "ab_pair_id": ab_pair_id,
        "ab_role": ab_role,
        "artifact_root": str(root),
        "profile_id": profile_id,
        "profile_version": str(tool_surface.get("profile_version") or ""),
        "profile_hash": str(tool_surface.get("profile_hash") or ""),
        "descriptor_hash": str(tool_surface.get("descriptor_hash") or ""),
        "route_table_hash": str(tool_surface.get("route_table_hash") or ""),
        "render_policy_hash": str(tool_surface.get("render_policy_hash") or ""),
        "workspace_snapshot_id": str(merged_tags.get("workspace_snapshot_id") or ""),
        "task_contract_hash": str(merged_tags.get("task_contract_hash") or ""),
        "model": str(merged_tags.get("model") or manifest.get("model") or transcript.model or ""),
        "effort": str(merged_tags.get("effort") or ""),
        "budget_profile": str(merged_tags.get("budget_profile") or ""),
        "provider_seed": str(merged_tags.get("provider_seed") or ""),
        "provider_seed_supported": bool(merged_tags.get("provider_seed_supported")),
        "lane_status": status,
        "accepted_finish_status": _accepted_finish_status(outputs),
        "request_count": len(inventory_records),
        "provider_tool_names": _provider_tool_names(tool_surface, inventory_records),
        "provider_visible_schema_bytes": _json_bytes(tool_surface.get("entries") or []),
        "provider_request_inventory_bytes": _json_bytes(inventory_records),
        "provider_visible_output_bytes": render_metrics["output_bytes"],
        "provider_visible_output_chars": render_metrics["output_chars"],
        "renderer_ids": render_metrics["renderer_ids"],
        "render_output_count": render_metrics["output_count"],
        "render_leak_ok": render_metrics["leak_ok"],
        "render_leak_fields": render_metrics["leak_fields"],
        "provider_inventory_forbidden_ok": provider_inventory_forbidden_ok,
        "hidden_steering_markers": hidden_steering,
        "provider_visible_forbidden_scan_ok": provider_inventory_forbidden_ok and render_metrics["leak_ok"],
        "pairing_valid": validation.valid,
        "call_count": validation.call_count,
        "output_count": validation.output_count,
        "every_call_has_exactly_one_output": validation.valid and validation.call_count == validation.output_count,
        "first_write_latency": _call_latency(first_write),
        "first_write_turn": _turn_index(first_write),
        "probe_count_before_first_write": sum(1 for call in before_first_write if call.tool_name in READ_PROBE_TOOL_NAMES),
        "command_count_before_first_write": sum(1 for call in before_first_write if call.tool_name in COMMAND_TOOL_NAMES),
        "read_list_alias_count_before_first_write": sum(1 for call in before_first_write if call.tool_name in READ_LIST_ALIAS_TOOL_NAMES),
        "mutation_count": sum(1 for call in calls if call.tool_name in WRITE_TOOL_NAMES),
        "first_verifier_latency": _call_latency(first_verifier),
        "first_verifier_turn": _turn_index(first_verifier),
        "failed_verifier_to_next_edit_latency": failure_to_edit_latency,
        "verifier_evidence_preserved": verifier_evidence_preserved,
        "unknown_tool_count": _route_count(route_rows, "unknown"),
        "argument_adapter_failure_count": _adapter_failure_count(outputs),
        "unsupported_capability_count": _unsupported_capability_count(outputs),
        "synthetic_error_count": sum(1 for item in outputs if item.status == "synthetic_error"),
        "sidecar_artifacts_present": sidecars["present"],
        "missing_sidecar_artifacts": sidecars["missing"],
        "proof_replay_status": {
            "proof_manifest_present": (root / "proof-manifest.json").is_file(),
            "transcript_hash_matches_manifest": str(manifest.get("transcript_hash") or "") == native_transcript_hash(transcript),
            "evidence_observation_present": (root / "native-evidence-observation.json").is_file(),
        },
    }
    row["row_ok_for_ab"] = _row_ok_for_ab(row)
    return row


def write_tool_surface_ab_report(
    output_path: object,
    *,
    baseline_artifact_root: object,
    candidate_artifact_root: object,
    ab_pair_id: str,
    workspace_snapshot_id: str = "",
    task_contract_hash: str = "",
    model: str = "",
    effort: str = "",
    budget_profile: str = "",
    provider_seed: str = "",
    provider_seed_supported: bool = False,
    baseline_tags: Mapping[str, object] | None = None,
    candidate_tags: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build and write a tool-surface A/B report JSON artifact."""

    report = build_tool_surface_ab_report(
        baseline_artifact_root=baseline_artifact_root,
        candidate_artifact_root=candidate_artifact_root,
        ab_pair_id=ab_pair_id,
        workspace_snapshot_id=workspace_snapshot_id,
        task_contract_hash=task_contract_hash,
        model=model,
        effort=effort,
        budget_profile=budget_profile,
        provider_seed=provider_seed,
        provider_seed_supported=provider_seed_supported,
        baseline_tags=baseline_tags,
        candidate_tags=candidate_tags,
    )
    path = Path(str(output_path)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _ab_exclusion_reasons(rows: tuple[dict[str, object], ...]) -> list[str]:
    reasons: list[str] = []
    profile_ids = {str(row.get("profile_id") or "") for row in rows}
    if MEW_LEGACY_PROFILE_ID not in profile_ids:
        reasons.append("missing_mew_legacy_profile")
    if CODEX_HOT_PATH_PROFILE_ID not in profile_ids:
        reasons.append("missing_codex_hot_path_profile")
    if any(not str(row.get("workspace_snapshot_id") or "") for row in rows):
        reasons.append("missing_workspace_snapshot_id")
    if any(not str(row.get("task_contract_hash") or "") for row in rows):
        reasons.append("missing_task_contract_hash")
    if len({str(row.get("workspace_snapshot_id") or "") for row in rows}) != 1:
        reasons.append("workspace_snapshot_mismatch")
    if len({str(row.get("task_contract_hash") or "") for row in rows}) != 1:
        reasons.append("task_contract_hash_mismatch")
    if not all(row.get("row_ok_for_ab") is True for row in rows):
        reasons.append("row_gate_failed")
    return reasons


def _comparison_summary(
    rows: tuple[dict[str, object], ...],
    *,
    ab_comparable: bool,
    exclusion_reasons: list[str],
) -> dict[str, object]:
    by_profile = {str(row.get("profile_id") or ""): row for row in rows}
    baseline = by_profile.get(MEW_LEGACY_PROFILE_ID) or rows[0]
    candidate = by_profile.get(CODEX_HOT_PATH_PROFILE_ID) or rows[-1]
    return {
        "ab_comparable": ab_comparable,
        "exclusion_reasons": list(exclusion_reasons),
        "workspace_snapshot_ids": sorted({str(row.get("workspace_snapshot_id") or "") for row in rows}),
        "task_contract_hashes": sorted({str(row.get("task_contract_hash") or "") for row in rows}),
        "output_bytes_delta_candidate_minus_baseline": int(candidate.get("provider_visible_output_bytes") or 0)
        - int(baseline.get("provider_visible_output_bytes") or 0),
        "schema_bytes_delta_candidate_minus_baseline": int(candidate.get("provider_visible_schema_bytes") or 0)
        - int(baseline.get("provider_visible_schema_bytes") or 0),
        "probe_count_before_first_write_delta_candidate_minus_baseline": int(
            candidate.get("probe_count_before_first_write") or 0
        )
        - int(baseline.get("probe_count_before_first_write") or 0),
        "candidate_hidden_steering_marker_count": len(candidate.get("hidden_steering_markers") or []),
        "candidate_render_leak_ok": candidate.get("render_leak_ok") is True,
        "candidate_pairing_valid": candidate.get("pairing_valid") is True,
    }


def _load_native_transcript(path: Path) -> NativeTranscript:
    payload = _load_json_mapping(path)
    return NativeTranscript(
        lane_attempt_id=str(payload.get("lane_attempt_id") or ""),
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
        items=tuple(_native_item(item) for item in payload.get("items") or [] if isinstance(item, Mapping)),
    )


def _native_item(item: Mapping[str, object]) -> NativeTranscriptItem:
    return NativeTranscriptItem(
        sequence=int(item.get("sequence") or 0),
        turn_id=str(item.get("turn_id") or ""),
        kind=str(item.get("kind") or ""),  # type: ignore[arg-type]
        lane_attempt_id=str(item.get("lane_attempt_id") or ""),
        provider=str(item.get("provider") or ""),
        model=str(item.get("model") or ""),
        response_id=str(item.get("response_id") or ""),
        provider_item_id=str(item.get("provider_item_id") or ""),
        output_index=int(item.get("output_index") or 0),
        call_id=str(item.get("call_id") or ""),
        tool_name=str(item.get("tool_name") or ""),
        arguments_json_text=str(item.get("arguments_json_text") or ""),
        custom_input_text=str(item.get("custom_input_text") or ""),
        output_text_or_ref=str(item.get("output_text_or_ref") or ""),
        status=str(item.get("status") or ""),
        is_error=bool(item.get("is_error")),
        raw_ref=str(item.get("raw_ref") or ""),
        encrypted_reasoning_ref=str(item.get("encrypted_reasoning_ref") or ""),
        metrics_ref=str(item.get("metrics_ref") or ""),
        content_refs=tuple(str(ref) for ref in item.get("content_refs") or ()),
        evidence_refs=tuple(str(ref) for ref in item.get("evidence_refs") or ()),
        sidecar_refs=tuple(str(ref) for ref in item.get("sidecar_refs") or ()),
    )


def _load_json_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def _jsonl_rows(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, Mapping):
            rows.append(dict(data))
    return tuple(rows)


def _mapping_rows(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_tool_surface(inventory_records: tuple[dict[str, object], ...]) -> dict[str, object]:
    for record in inventory_records:
        tool_surface = record.get("tool_surface")
        if isinstance(tool_surface, Mapping):
            return dict(tool_surface)
    return {}


def _provider_tool_names(
    tool_surface: Mapping[str, object],
    inventory_records: tuple[dict[str, object], ...],
) -> list[str]:
    names = tool_surface.get("provider_tool_names")
    if isinstance(names, list):
        return [str(name) for name in names]
    for record in inventory_records:
        surface = record.get("tool_surface")
        if isinstance(surface, Mapping) and isinstance(surface.get("provider_tool_names"), list):
            return [str(name) for name in surface.get("provider_tool_names") or []]
    return []


def _render_metrics(render_rows: tuple[dict[str, object], ...]) -> dict[str, object]:
    leak_fields = sorted(
        {
            str(field)
            for row in render_rows
            for field in (row.get("leak_fields") if isinstance(row.get("leak_fields"), list) else [])
        }
    )
    return {
        "output_count": len(render_rows),
        "output_bytes": sum(int(row.get("output_bytes") or 0) for row in render_rows),
        "output_chars": sum(int(row.get("output_chars") or 0) for row in render_rows),
        "renderer_ids": sorted({str(row.get("renderer_id") or "") for row in render_rows if row.get("renderer_id")}),
        "leak_ok": bool(render_rows) and all(row.get("leak_ok") is True for row in render_rows),
        "leak_fields": leak_fields,
    }


def _provider_inventory_forbidden_ok(inventory_records: tuple[dict[str, object], ...]) -> bool:
    if not inventory_records:
        return False
    for record in inventory_records:
        report = record.get("provider_visible_forbidden_fields")
        if not isinstance(report, Mapping):
            return False
        if report.get("ok") is not True:
            return False
    return True


def _hidden_steering_markers(inventory_records: tuple[dict[str, object], ...]) -> list[str]:
    hits: set[str] = set()
    for marker in FORBIDDEN_HOT_PATH_STEERING_MARKERS:
        for record in inventory_records:
            report = record.get("provider_visible_forbidden_fields")
            detected = report.get("detected") if isinstance(report, Mapping) else ()
            if isinstance(detected, list) and marker in {str(item) for item in detected}:
                hits.add(marker)
    return sorted(hits)


def _first_call(
    calls: tuple[NativeTranscriptItem, ...],
    tool_names: frozenset[str],
) -> NativeTranscriptItem | None:
    return next((call for call in calls if call.tool_name in tool_names), None)


def _first_verifier_call(calls: tuple[NativeTranscriptItem, ...]) -> NativeTranscriptItem | None:
    return next((call for call in calls if _native_call_is_verifier(call)), None)


def _call_latency(item: NativeTranscriptItem | None) -> dict[str, object]:
    if item is None:
        return {"turn_index": None, "call_id": "", "tool_name": "", "sequence": None}
    return {
        "turn_index": _turn_index(item),
        "call_id": item.call_id,
        "tool_name": item.tool_name,
        "sequence": item.sequence,
    }


def _turn_index(item: NativeTranscriptItem | None) -> int | None:
    if item is None:
        return None
    match = re.search(r"(\d+)$", item.turn_id)
    if match:
        return int(match.group(1))
    return item.sequence


def _failed_verifier_to_next_edit_latency(
    calls: tuple[NativeTranscriptItem, ...],
    outputs: tuple[NativeTranscriptItem, ...],
) -> dict[str, object]:
    calls_by_id = {call.call_id: call for call in calls}
    failed_verifier_output = next(
        (
            output
            for output in outputs
            if output.call_id in calls_by_id
            and _native_call_is_verifier(calls_by_id[output.call_id])
            and (output.is_error or output.status not in {"completed"})
        ),
        None,
    )
    if failed_verifier_output is None:
        return {"failed_verifier_call_id": "", "next_edit_call_id": "", "latency_turns": None, "latency_sequences": None}
    next_edit = next(
        (
            call
            for call in calls
            if call.sequence > failed_verifier_output.sequence and call.tool_name in WRITE_TOOL_NAMES
        ),
        None,
    )
    if next_edit is None:
        return {
            "failed_verifier_call_id": failed_verifier_output.call_id,
            "next_edit_call_id": "",
            "latency_turns": None,
            "latency_sequences": None,
        }
    return {
        "failed_verifier_call_id": failed_verifier_output.call_id,
        "next_edit_call_id": next_edit.call_id,
        "latency_turns": (_turn_index(next_edit) or 0) - (_turn_index(failed_verifier_output) or 0),
        "latency_sequences": next_edit.sequence - failed_verifier_output.sequence,
    }


def _verifier_evidence_preserved(
    calls: tuple[NativeTranscriptItem, ...],
    outputs: tuple[NativeTranscriptItem, ...],
    *,
    evidence_summary: Mapping[str, object],
    evidence_observation_present: bool,
) -> bool:
    verifier_call_ids = {call.call_id for call in calls if _native_call_is_verifier(call)}
    if not verifier_call_ids:
        return True
    if not evidence_observation_present:
        return False
    verifier_outputs = [output for output in outputs if output.call_id in verifier_call_ids]
    if not verifier_outputs:
        return False
    if any(output.evidence_refs or output.content_refs for output in verifier_outputs):
        return True
    return int(evidence_summary.get("known_tool_evidence_ref_count") or 0) > 0


def _accepted_finish_status(outputs: tuple[NativeTranscriptItem, ...]) -> str:
    finish_outputs = [item for item in outputs if item.kind == "finish_output"]
    if not finish_outputs:
        return "missing"
    latest = finish_outputs[-1]
    if latest.status == "completed" and not latest.is_error:
        return "accepted"
    return latest.status or "blocked"


def _route_count(route_rows: tuple[dict[str, object], ...], needle: str) -> int:
    lowered = needle.casefold()
    return sum(1 for row in route_rows if lowered in json.dumps(row, sort_keys=True).casefold())


def _adapter_failure_count(outputs: tuple[NativeTranscriptItem, ...]) -> int:
    return sum(1 for output in outputs if "adapter error" in output.output_text_or_ref.casefold())


def _unsupported_capability_count(outputs: tuple[NativeTranscriptItem, ...]) -> int:
    return sum(1 for output in outputs if "not supported" in output.output_text_or_ref.casefold())


def _sidecar_status(root: Path) -> dict[str, object]:
    missing = [name for name in REQUIRED_SIDECAR_ARTIFACTS if not (root / name).is_file()]
    return {"present": not missing, "missing": missing}


def _row_ok_for_ab(row: Mapping[str, object]) -> bool:
    common_ok = all(
        (
            bool(row.get("profile_id")),
            bool(row.get("profile_hash")),
            bool(row.get("descriptor_hash")),
            row.get("pairing_valid") is True,
            row.get("every_call_has_exactly_one_output") is True,
            row.get("render_leak_ok") is True,
            row.get("sidecar_artifacts_present") is True,
            row.get("verifier_evidence_preserved") is True,
            _mapping(row.get("proof_replay_status")).get("transcript_hash_matches_manifest") is True,
        )
    )
    if not common_ok:
        return False
    if str(row.get("profile_id") or "") != CODEX_HOT_PATH_PROFILE_ID:
        return True
    return row.get("provider_inventory_forbidden_ok") is True


def _json_bytes(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


__all__ = [
    "TOOL_SURFACE_AB_REPORT_SCHEMA_VERSION",
    "build_tool_surface_ab_report",
    "build_tool_surface_run_report",
    "write_tool_surface_ab_report",
]
