"""Fast contract checks for M6.24 implement_v2 hot-path collapse.

This module intentionally avoids Harbor and long live model runs. It validates
the resident sidecar/projection contract from saved implement_v2 artifacts and
requires a small micro next-action decision before a costly `step-check-10min`
can be spent.

The micro decision is hybrid:

- reuse a saved fixture when its prompt/projection hashes still match;
- otherwise refresh it with one bounded live model call and save the response as
  the new fixture evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping

from ..model_backends import (
    call_model_json,
    load_model_auth,
    model_backend_default_base_url,
    model_backend_default_model,
)
from .native_tool_harness import _native_call_is_verifier, _native_loop_control_state
from .completion_resolver import COMPLETION_RESOLVER_DECISIONS_FILE
from .native_sidecar_projection import build_compact_native_sidecar_digest
from .native_transcript import IMPLEMENT_V2_NATIVE_RUNTIME_ID, NativeTranscript, NativeTranscriptItem
from .native_transcript import native_function_call_argument_metrics, native_transcript_hash, validate_native_transcript_pairing
from .tool_lab import resolve_implement_v2_manifest_path
from .types import search_text_output_has_line_anchor
from .v2_runtime import _render_prompt_history_json
from .workframe import (
    WORKFRAME_RED_MAX_BYTES,
    WorkFrameInputs,
    canonical_json,
    canonicalize_workframe_inputs,
    workframe_output_hash,
)
from .workframe_variants import reduce_workframe_with_variant
from .workframe_variants import (
    CommonWorkFrameInputs,
    canonicalize_common_workframe_inputs,
    common_workframe_inputs_from_workframe_inputs,
    project_workframe_with_variant,
)

HOT_PATH_FASTCHECK_SCHEMA_VERSION = 1
DEFAULT_HOT_PATH_BASELINE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "M6_24_HOT_PATH_PHASE0_BASELINE.json"
)
PHASE0_GREEN_TOTAL_RATIO = 1.10
PHASE0_YELLOW_TOTAL_RATIO = 1.25
PHASE0_RED_PER_TURN_GROWTH_RATIO = 1.50
NEXT_ACTION_CATEGORIES = (
    "patch/edit",
    "run_verifier",
    "inspect_latest_failure",
    "cheap_probe",
    "finish_with_evidence",
    "blocked",
    "invalid",
)


@dataclass(frozen=True)
class HotPathCheck:
    name: str
    status: str
    message: str
    details: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": dict(self.details),
        }


def run_hot_path_fastcheck(
    artifact: object,
    *,
    micro_next_action: object | None = None,
    refresh_micro_next_action: bool = False,
    auth_path: object | None = "auth.json",
    model_backend: str = "codex",
    model: str = "",
    base_url: str = "",
    model_timeout: float = 60.0,
    micro_next_action_output: object | None = None,
    micro_model_callable: Callable[[str], dict[str, object]] | None = None,
    expected_categories: Iterable[str] = (),
    max_active_todo_bytes: int = 2048,
    max_sidecar_total_bytes: int = 262144,
    max_sidecar_per_turn_growth_bytes: int = 32768,
    baseline: object | None = None,
) -> dict[str, object]:
    """Run the M6.24 HOT_PATH_COLLAPSE fast contract checks.

    A saved `micro_next_action` fixture is reused only when its hashes match the
    current artifact projection. Missing or stale fixtures are refreshed through
    one bounded live model call, then saved for replayable future checks.
    """

    manifest_path = resolve_implement_v2_manifest_path(artifact)
    artifact_path = Path(str(artifact or "")).expanduser()
    manifest = _load_manifest_json(manifest_path)
    if _is_native_transcript_artifact(artifact_path=artifact_path, manifest_path=manifest_path, manifest=manifest):
        return _run_native_hot_path_fastcheck(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            manifest=manifest,
            baseline=baseline,
        )

    history_path = resolve_implement_v2_history_path(artifact_path, manifest_path)
    micro_read_path, micro_write_path = _resolve_micro_fixture_paths(
        manifest_path=manifest_path,
        micro_next_action=micro_next_action,
        micro_next_action_output=micro_next_action_output,
    )

    checks: list[HotPathCheck] = []
    history = _load_history_json(history_path)
    baseline_data = _load_baseline_json(baseline)
    expected = _expected_micro_categories(expected_categories)

    checks.append(_check_manifest_lane(manifest))
    checks.append(_check_hot_path_metrics(manifest))
    workframe_bundle = _load_workframe_bundle(artifact_path=artifact_path, manifest_path=manifest_path, manifest=manifest)
    checks.append(_check_prompt_leaks(manifest, workframe_bundle=workframe_bundle, max_active_todo_bytes=max_active_todo_bytes))
    checks.append(_check_workframe_replay(workframe_bundle, manifest))
    checks.append(_check_workframe_invariants(workframe_bundle))
    checks.append(_check_workframe_evidence_refs(workframe_bundle))
    checks.append(_check_workframe_reentry_stability(workframe_bundle))
    checks.append(_check_legacy_projection_rejected(history))
    checks.append(
        _check_sidecar_metrics(
            manifest,
            baseline=baseline_data,
            max_total_bytes=max_sidecar_total_bytes,
            max_per_turn_growth_bytes=max_sidecar_per_turn_growth_bytes,
        )
    )
    checks.append(_check_latest_actionable_failure_shape(history))
    static_checks_pass = all(check.status == "pass" for check in checks)
    if static_checks_pass:
        micro_fixture, micro_path, micro_refresh = _load_or_refresh_micro_next_action_fixture(
            artifact_path=artifact_path,
            manifest_path=manifest_path,
            history_path=history_path,
            manifest=manifest,
            history=history,
            workframe_bundle=workframe_bundle,
            micro_read_path=micro_read_path,
            micro_write_path=micro_write_path,
            refresh_micro_next_action=refresh_micro_next_action,
            auth_path=auth_path,
            model_backend=model_backend,
            model=model,
            base_url=base_url,
            model_timeout=model_timeout,
            expected_categories=expected,
            micro_model_callable=micro_model_callable,
        )
        checks.append(_check_micro_next_action(micro_fixture, expected_categories=expected))
    else:
        micro_path = micro_read_path if micro_read_path.is_file() else micro_write_path
        micro_refresh = {"mode": "skipped", "reason": "static_checks_failed"}
        checks.append(
            _check(
                "micro_next_action",
                False,
                "skipped because static phase-contract checks failed",
                {"expected_categories": list(expected), "skipped": True},
            )
        )

    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return {
        "schema_version": HOT_PATH_FASTCHECK_SCHEMA_VERSION,
        "status": status,
        "artifact": str(artifact_path),
        "manifest_path": str(manifest_path),
        "history_path": str(history_path),
        "micro_next_action_path": str(micro_path),
        "micro_next_action_refresh": micro_refresh,
        "checks": [check.as_dict() for check in checks],
        "metrics": {
            "hot_path_projection": _safe_mapping((manifest.get("metrics") or {}).get("hot_path_projection")),
            "resident_sidecar_state": _safe_mapping((manifest.get("metrics") or {}).get("resident_sidecar_state")),
            "workframe": _safe_mapping((manifest.get("metrics") or {}).get("workframe")),
            "baseline": baseline_data,
            "micro_next_action": {
                "category": _micro_next_action_category(micro_fixture) if static_checks_pass else "",
                "expected_categories": list(expected),
            },
        },
    }


def format_hot_path_fastcheck_text(result: dict[str, object]) -> str:
    lines = [
        "implement_v2 hot-path fastcheck",
        f"status: {result.get('status')}",
        f"manifest: {result.get('manifest_path')}",
        f"history: {result.get('history_path')}",
        f"transcript: {result.get('transcript_path')}",
        f"micro_next_action: {result.get('micro_next_action_path')}",
        f"micro_refresh: {_format_micro_refresh_line(result.get('micro_next_action_refresh'))}",
        "",
        "checks:",
    ]
    for check in result.get("checks") or []:
        if not isinstance(check, dict):
            continue
        lines.append(f"- {check.get('status')} {check.get('name')}: {check.get('message')}")
    return "\n".join(lines)


def _is_native_transcript_artifact(
    *,
    artifact_path: Path,
    manifest_path: Path,
    manifest: Mapping[str, object],
) -> bool:
    if str(manifest.get("runtime_id") or "") == IMPLEMENT_V2_NATIVE_RUNTIME_ID:
        return True
    if _native_manifest_transport_is_provider_native(manifest):
        return True
    metrics = _safe_mapping(manifest.get("metrics"))
    if metrics.get("provider_native_tool_loop") is True:
        return True
    return _resolve_native_transcript_path(artifact_path=artifact_path, manifest_path=manifest_path).is_file()


def _run_native_hot_path_fastcheck(
    *,
    artifact_path: Path,
    manifest_path: Path,
    manifest: dict[str, object],
    baseline: object | None,
) -> dict[str, object]:
    transcript_path = _resolve_native_transcript_path(artifact_path=artifact_path, manifest_path=manifest_path)
    response_items_path = transcript_path.parent / "response_items.jsonl"
    baseline_data = _load_baseline_json(baseline)
    transcript_payload: dict[str, object] = {}
    transcript: NativeTranscript | None = None
    transcript_error = ""
    try:
        transcript_payload = _load_native_transcript_payload(transcript_path)
        transcript = _native_transcript_from_payload(transcript_payload)
    except Exception as exc:
        transcript_error = str(exc)

    checks: list[HotPathCheck] = [
        _check_native_transcript_read(transcript_path, transcript=transcript, error=transcript_error),
    ]
    if transcript is not None:
        checks.append(_check_native_manifest_contract(manifest, transcript=transcript, transcript_payload=transcript_payload))
        checks.append(_check_native_pairing(transcript))
        checks.append(_check_native_response_items(response_items_path, transcript=transcript))
        checks.append(_check_native_trace_summary(artifact_path=artifact_path, manifest_path=manifest_path, transcript=transcript))
        checks.append(_check_native_controller_steering_outputs(transcript))
        checks.append(_check_native_generation_observation(transcript))
        checks.append(_check_native_loop_control_replay(transcript))
        checks.append(_check_native_search_text_anchor_projection(transcript))
        provider_requests = _native_provider_requests(artifact_path=artifact_path, manifest_path=manifest_path)
        checks.append(_check_native_compact_digest_replay(provider_requests, fallback_transcript=transcript))
        checks.append(_check_native_provider_visible_state(provider_requests))
        checks.append(
            _check_native_resolver_decisions(
                manifest_path=manifest_path,
                manifest=manifest,
                transcript=transcript,
            )
        )
        checks.append(_check_native_evidence_observation(manifest_path=manifest_path, manifest=manifest, transcript=transcript))
    else:
        checks.extend(
            [
                _check("native_manifest_contract", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_pairing", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_response_items_match", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_trace_summary", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_controller_steering_outputs", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_generation_observation", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_loop_control_replay", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_search_text_anchor_projection", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_compact_digest_replay", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_provider_visible_state", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_resolver_decisions", False, "native transcript is unreadable", {"skipped": True}),
                _check("native_evidence_observation", False, "native transcript is unreadable", {"skipped": True}),
            ]
        )
    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return {
        "schema_version": HOT_PATH_FASTCHECK_SCHEMA_VERSION,
        "status": status,
        "artifact": str(artifact_path),
        "manifest_path": str(manifest_path),
        "history_path": "",
        "transcript_path": str(transcript_path),
        "response_items_path": str(response_items_path),
        "micro_next_action_path": "",
        "micro_next_action_refresh": {"mode": "skipped", "reason": "native_transcript_mode"},
        "checks": [check.as_dict() for check in checks],
        "metrics": {
            "native_transcript": _native_transcript_metrics(transcript) if transcript is not None else {},
            "native_trace": _native_trace_summary(artifact_path=artifact_path, manifest_path=manifest_path, transcript=transcript),
            "native_generation": _native_generation_metrics(transcript) if transcript is not None else {},
            "baseline": baseline_data,
            "micro_next_action": {"category": "", "expected_categories": []},
        },
    }


def _resolve_native_transcript_path(*, artifact_path: Path, manifest_path: Path) -> Path:
    candidates = (
        manifest_path.parent / "response_transcript.json",
        artifact_path / "response_transcript.json",
        artifact_path / "implement_v2" / "response_transcript.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(strict=False)
    search_root = artifact_path if artifact_path.exists() else manifest_path.parent
    recursive = sorted(search_root.rglob("response_transcript.json")) if search_root.is_dir() else []
    if recursive:
        return recursive[0].resolve(strict=False)
    return (manifest_path.parent / "response_transcript.json").resolve(strict=False)


def _load_native_transcript_payload(path: Path) -> dict[str, object]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"expected native transcript JSON object: {path}")
    return dict(payload)


def _native_transcript_from_payload(payload: Mapping[str, object]) -> NativeTranscript:
    return NativeTranscript(
        lane_attempt_id=str(payload.get("lane_attempt_id") or ""),
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
        items=tuple(_native_transcript_item_from_mapping(item) for item in payload.get("items") or [] if isinstance(item, Mapping)),
    )


def _native_transcript_item_from_mapping(item: Mapping[str, object]) -> NativeTranscriptItem:
    return NativeTranscriptItem(
        sequence=_nonnegative_int(item.get("sequence")),
        turn_id=str(item.get("turn_id") or ""),
        kind=str(item.get("kind") or ""),  # type: ignore[arg-type]
        lane_attempt_id=str(item.get("lane_attempt_id") or ""),
        provider=str(item.get("provider") or ""),
        model=str(item.get("model") or ""),
        response_id=str(item.get("response_id") or ""),
        provider_item_id=str(item.get("provider_item_id") or ""),
        output_index=_nonnegative_int(item.get("output_index")),
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


def _check_native_transcript_read(path: Path, *, transcript: NativeTranscript | None, error: str) -> HotPathCheck:
    ok = transcript is not None and bool(transcript.items)
    return _check(
        "native_transcript_read",
        ok,
        "native transcript is readable" if ok else "native transcript is missing, empty, or invalid",
        {"path": str(path), "item_count": len(transcript.items) if transcript else 0, "error": error},
    )


def _check_native_manifest_contract(
    manifest: Mapping[str, object],
    *,
    transcript: NativeTranscript,
    transcript_payload: Mapping[str, object],
) -> HotPathCheck:
    metrics = _safe_mapping(manifest.get("metrics"))
    pairing = _safe_mapping(manifest.get("pairing"))
    computed_hash = native_transcript_hash(transcript)
    payload_hash = str(transcript_payload.get("hash") or "")
    checks = {
        "native_runtime_id": str(manifest.get("runtime_id") or "") == IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "native_transport": _native_manifest_transport_is_provider_native(manifest),
        "provider_native_tool_loop": metrics.get("provider_native_tool_loop") is True,
        "model_json_main_path_not_detected": metrics.get("model_json_main_path_detected") is not True,
        "manifest_transcript_hash_matches": str(manifest.get("transcript_hash") or "") == computed_hash,
        "payload_transcript_hash_matches": payload_hash == computed_hash,
        "manifest_pairing_valid": pairing.get("valid") is True or metrics.get("pairing_valid") is True,
    }
    ok = all(checks.values())
    return _check(
        "native_manifest_contract",
        ok,
        "native manifest matches authoritative transcript" if ok else "native manifest does not match authoritative transcript",
        {
            **checks,
            "runtime_id": manifest.get("runtime_id"),
            "transport_kind": manifest.get("transport_kind"),
            "native_transport_kind": manifest.get("native_transport_kind") or metrics.get("native_transport_kind"),
            "transcript_hash": computed_hash,
            "manifest_transcript_hash": manifest.get("transcript_hash"),
            "payload_transcript_hash": payload_hash,
        },
    )


def _check_native_pairing(transcript: NativeTranscript) -> HotPathCheck:
    result = validate_native_transcript_pairing(transcript)
    return _check(
        "native_pairing",
        result.valid,
        "native function calls and outputs are paired" if result.valid else "native function call/output pairing is invalid",
        result.as_dict(),
    )


def _check_native_response_items(path: Path, *, transcript: NativeTranscript) -> HotPathCheck:
    error = ""
    response_items: list[object] = []
    try:
        response_items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:
        error = str(exc)
    transcript_items = [item.as_dict() for item in transcript.items]
    ok = bool(response_items) and response_items == transcript_items
    return _check(
        "native_response_items_match",
        ok,
        "response_items.jsonl matches response_transcript.json"
        if ok
        else "response_items.jsonl does not match response_transcript.json",
        {
            "path": str(path),
            "response_item_count": len(response_items),
            "transcript_item_count": len(transcript_items),
            "error": error,
        },
    )


def _check_native_trace_summary(
    *,
    artifact_path: Path,
    manifest_path: Path,
    transcript: NativeTranscript,
) -> HotPathCheck:
    summary = _native_trace_summary(artifact_path=artifact_path, manifest_path=manifest_path, transcript=transcript)
    parse_error_count = _nonnegative_int(summary.get("parse_error_count"))
    edit_count = _nonnegative_int(summary.get("edit_count"))
    verifier_count = _nonnegative_int(summary.get("verifier_count"))
    has_hot_path_shape = edit_count > 0 and verifier_count > 0
    ok = parse_error_count == 0 and has_hot_path_shape
    if ok:
        message = "native trace summary is available, parse-clean, and contains edit plus verifier"
    elif parse_error_count:
        message = "native trace summary has parse errors"
    elif edit_count <= 0 and verifier_count <= 0:
        message = "native trace summary has no source mutation or verifier calls"
    elif edit_count <= 0:
        message = "native trace summary has no source mutation calls"
    else:
        message = "native trace summary has no verifier calls"
    return _check(
        "native_trace_summary",
        ok,
        message,
        summary,
    )


def _check_native_controller_steering_outputs(transcript: NativeTranscript) -> HotPathCheck:
    markers = (
        "first-write due overrun",
        "prewrite probe plateau",
        "perform a source mutation",
        "enough read/probe evidence has been gathered",
        "max_additional_probe_turns",
    )
    violations: list[dict[str, object]] = []
    for item in transcript.items:
        if not item.kind.endswith("_output"):
            continue
        text = str(item.output_text_or_ref or "").casefold()
        hits = [marker for marker in markers if marker in text]
        if hits:
            violations.append(
                {
                    "turn_id": item.turn_id,
                    "call_id": item.call_id,
                    "tool_name": item.tool_name,
                    "status": item.status,
                    "markers": hits,
                    "summary": item.output_text_or_ref[:300],
                }
            )
    ok = not violations
    return _check(
        "native_controller_steering_outputs",
        ok,
        "native transcript tool outputs do not contain controller-authored next-action steering"
        if ok
        else "native transcript tool outputs contain controller-authored next-action steering",
        {"violations": violations[:10]},
    )


def _native_trace_summary(
    *,
    artifact_path: Path,
    manifest_path: Path,
    transcript: NativeTranscript | None,
) -> dict[str, object]:
    for candidate in (
        manifest_path.parent / "normalized-trace" / "summary.json",
        artifact_path / "normalized-trace" / "summary.json",
    ):
        if candidate.is_file():
            data = _load_json(candidate)
            if isinstance(data, dict):
                return dict(data)
    if transcript is None:
        return {}
    calls = [item for item in transcript.items if item.kind in {"function_call", "custom_tool_call", "finish_call"}]
    return {
        "source": "computed_from_native_transcript",
        "turn_count": len({item.turn_id for item in transcript.items if item.turn_id}),
        "command_count": sum(1 for item in calls if item.tool_name in {"run_command", "run_tests"}),
        "edit_count": sum(1 for item in calls if item.tool_name in {"write_file", "edit_file", "apply_patch"}),
        "verifier_count": sum(1 for item in calls if _native_call_is_verifier(item)),
        "parse_error_count": sum(1 for item in transcript.items if _native_trace_item_is_protocol_parse_error(item)),
    }


def _native_trace_item_is_protocol_parse_error(item: NativeTranscriptItem) -> bool:
    if _native_finish_output_is_protocol_invalid(item):
        return True
    if not item.is_error or item.status not in {"invalid", "synthetic_error"}:
        return False
    text = str(item.output_text_or_ref or "").casefold()
    return any(
        marker in text
        for marker in (
            "invalid native response",
            "invalid json arguments",
            "model json",
            "parse error",
            "protocol_error",
            "schema invalid",
        )
    )


def _check_native_loop_control_replay(transcript: NativeTranscript) -> HotPathCheck:
    state = _native_loop_control_state(list(transcript.items), current_turn_index=_native_next_turn_index(transcript.items))
    failed_verifier = bool(_safe_mapping(state.get("latest_failed_verifier")))
    pending_failed_verifier_repair = bool(
        failed_verifier
        and _nonnegative_int(state.get("post_failure_write_count")) == 0
        and _nonnegative_int(state.get("post_failure_probe_count")) >= 2
    )
    ok = not pending_failed_verifier_repair or state.get("verifier_repair_due") is True
    return _check(
        "native_loop_control_replay",
        ok,
        "native loop control replay reaches the expected repair policy"
        if ok
        else "native loop control replay failed to mark pending verifier repair",
        dict(state),
    )


def _check_native_search_text_anchor_projection(transcript: NativeTranscript) -> HotPathCheck:
    missing: list[dict[str, object]] = []
    checked = 0
    for item in transcript.items:
        if item.tool_name != "search_text" or not item.kind.endswith("_output") or item.status != "completed":
            continue
        match_count = _native_search_text_match_count(item.output_text_or_ref)
        if match_count <= 0:
            continue
        checked += 1
        if not search_text_output_has_line_anchor(item.output_text_or_ref):
            missing.append(
                {
                    "call_id": item.call_id,
                    "turn_id": item.turn_id,
                    "match_count": match_count,
                    "summary": item.output_text_or_ref[:300],
                }
            )
    ok = not missing
    return _check(
        "native_search_text_anchor_projection",
        ok,
        "positive native search_text outputs expose path:line anchors"
        if ok
        else "positive native search_text output is missing model-visible path:line anchors",
        {"checked_positive_searches": checked, "missing": missing[:5]},
    )


def _check_native_compact_digest_replay(
    provider_requests: tuple[dict[str, object], ...],
    *,
    fallback_transcript: NativeTranscript,
) -> HotPathCheck:
    if not provider_requests:
        return _check(
            "native_compact_digest_replay",
            True,
            "no provider request artifact present; compact digest replay skipped",
            {"skipped": True},
        )
    mismatches: list[dict[str, object]] = []
    checked = 0
    for index, request in enumerate(provider_requests, start=1):
        digest = _native_request_compact_digest(request)
        if not digest:
            mismatches.append({"request": index, "reason": "missing_compact_sidecar_digest"})
            continue
        transcript = _native_request_transcript(request, fallback_transcript=fallback_transcript)
        recomputed = build_compact_native_sidecar_digest(transcript)
        checked += 1
        if digest != recomputed:
            mismatches.append(
                {
                    "request": index,
                    "reason": "digest_mismatch",
                    "stored": digest.get("digest_hash"),
                    "recomputed": recomputed.get("digest_hash"),
                    "stored_transcript_hash": digest.get("transcript_hash"),
                    "recomputed_transcript_hash": recomputed.get("transcript_hash"),
                }
            )
    return _check(
        "native_compact_digest_replay",
        not mismatches and checked > 0,
        "provider request compact_sidecar_digest deterministically replays from transcript window"
        if not mismatches and checked > 0
        else "provider request compact_sidecar_digest does not replay from transcript window",
        {"checked_requests": checked, "mismatches": mismatches[:5]},
    )


def _check_native_provider_visible_state(provider_requests: tuple[dict[str, object], ...]) -> HotPathCheck:
    if not provider_requests:
        return _check(
            "native_provider_visible_state",
            True,
            "no provider request artifact present; provider-visible static gate skipped",
            {"skipped": True},
        )
    violations: list[dict[str, object]] = []
    checked = 0
    for index, request in enumerate(provider_requests, start=1):
        checked += 1
        digest = _native_request_compact_digest(request)
        task_payload = _native_request_task_payload(request)
        inventory = _safe_mapping(request.get("provider_request_inventory"))
        projection = _safe_mapping(digest.get("workframe_projection"))
        serialized_digest = json.dumps(digest, ensure_ascii=False, sort_keys=True)
        provider_visible = json.dumps(
            {
                "input_items": _native_request_input_items(request),
                "instructions": _native_request_instructions(request),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        transition_contract = _native_request_allows_transition_contract(task_payload, digest)
        if inventory.get("model_visible_sections") != ["native_transcript_window", "compact_sidecar_digest"]:
            violations.append(
                {
                    "request": index,
                    "reason": "unexpected_model_visible_sections",
                    "model_visible_sections": inventory.get("model_visible_sections"),
                }
            )
        if digest.get("provider_input_authority") != "transcript_window_plus_compact_sidecar_digest":
            violations.append(
                {
                    "request": index,
                    "reason": "wrong_provider_input_authority",
                    "provider_input_authority": digest.get("provider_input_authority"),
                }
            )
        if len(digest) > 16:
            violations.append({"request": index, "reason": "digest_top_level_key_cap", "key_count": len(digest)})
        digest_bytes = len(serialized_digest.encode("utf-8"))
        if digest_bytes > 6144:
            violations.append({"request": index, "reason": "digest_byte_cap", "bytes": digest_bytes})
        if len(projection) > 8:
            violations.append(
                {"request": index, "reason": "workframe_projection_key_cap", "key_count": len(projection)}
            )
        if not transition_contract:
            required_next_tokens = [
                token
                for token in ("required_next_kind", "required_next_evidence_refs", "needs_")
                if token in serialized_digest
            ]
            if required_next_tokens:
                violations.append(
                    {"request": index, "reason": "default_required_next_leak", "tokens": required_next_tokens}
                )
        forbidden_tokens = [
            token
            for token in (
                "persisted_lane_state",
                "frontier_state_update",
                "hard_runtime_frontier",
                "proof_manifest",
                "model_authored_todo",
                "model_authored_proof",
                "next_action_policy",
                "next_action",
                "required_next_action",
                "first_write_due",
                "first_write_due_overrun",
                "first_write_probe_threshold",
                "first_write_turn_threshold",
                "first_write_grace_probe_calls",
                "prewrite_probe_plateau",
                "max_additional_probe_turns",
            )
            if token in provider_visible or token in serialized_digest
        ]
        if forbidden_tokens:
            violations.append({"request": index, "reason": "legacy_state_leak", "tokens": forbidden_tokens})
        imperative_hints = _native_imperative_hint_leaks(projection)
        if imperative_hints:
            violations.append({"request": index, "reason": "imperative_instruction_hint", "hints": imperative_hints})
    return _check(
        "native_provider_visible_state",
        not violations and checked > 0,
        "provider-visible native request state is bounded and default required_next-free"
        if not violations and checked > 0
        else "provider-visible native request state drifted beyond native transcript window + compact digest",
        {"checked_requests": checked, "violations": violations[:10]},
    )


def _check_native_resolver_decisions(
    *,
    manifest_path: Path,
    manifest: Mapping[str, object],
    transcript: NativeTranscript,
) -> HotPathCheck:
    valid_finish_call_ids = _native_valid_finish_call_ids(transcript)
    finish_output_ids = {
        item.call_id
        for item in transcript.items
        if item.kind == "finish_output" and item.call_id and item.call_id in valid_finish_call_ids
    }
    decision_ref = str(manifest.get("resolver_decisions_ref") or "").strip()
    decision_sha = str(manifest.get("resolver_decisions_sha256") or "").strip()
    if not decision_ref:
        ok = not valid_finish_call_ids
        return _check(
            "native_resolver_decisions",
            ok,
            "no finish claim requires resolver decision artifact"
            if ok
            else "finish claim exists without resolver decision artifact",
            {
                "finish_call_ids": sorted(valid_finish_call_ids),
                "resolver_decisions_ref": "",
            },
        )
    decision_path = (manifest_path.parent / decision_ref).resolve(strict=False)
    rows, error = _load_jsonl_objects(decision_path)
    actual_sha = _file_sha256(decision_path) if decision_path.is_file() else ""
    row_finish_ids = {
        str(row.get("finish_call_id") or "").strip()
        for row in rows
        if str(row.get("finish_call_id") or "").strip()
    }
    row_output_ids = {
        str(row.get("finish_output_call_id") or "").strip()
        for row in rows
        if str(row.get("finish_output_call_id") or "").strip()
    }
    transcript_text = json.dumps([item.as_dict() for item in transcript.items], ensure_ascii=False, sort_keys=True)
    checks = {
        "path_exists": decision_path.is_file(),
        "sha_matches": bool(decision_sha) and decision_sha == actual_sha,
        "rows_present": bool(rows),
        "finish_calls_exact": row_finish_ids == valid_finish_call_ids,
        "finish_outputs_exact": row_output_ids == finish_output_ids,
        "decision_count_matches_finish_count": len(rows) == len(valid_finish_call_ids),
        "not_native_response_item": "completion_resolver" not in transcript_text,
        "expected_filename": decision_path.name == COMPLETION_RESOLVER_DECISIONS_FILE,
    }
    ok = all(checks.values())
    return _check(
        "native_resolver_decisions",
        ok,
        "resolver decisions replay from sidecar artifact and manifest hash"
        if ok
        else "resolver decision sidecar artifact is missing, stale, or not aligned with finish transcript",
        {
            **checks,
            "resolver_decisions_ref": decision_ref,
            "resolver_decisions_sha256": decision_sha,
            "actual_sha256": actual_sha,
            "row_count": len(rows),
            "finish_call_ids": sorted(valid_finish_call_ids),
            "row_finish_call_ids": sorted(row_finish_ids),
            "finish_output_ids": sorted(finish_output_ids),
            "row_finish_output_ids": sorted(row_output_ids),
            "load_error": error,
        },
    )


def _native_valid_finish_call_ids(transcript: NativeTranscript) -> set[str]:
    finish_outputs = {
        item.call_id: item
        for item in transcript.items
        if item.kind == "finish_output" and item.call_id
    }
    valid: set[str] = set()
    for item in transcript.items:
        if item.kind != "finish_call" or not item.call_id:
            continue
        output = finish_outputs.get(item.call_id)
        if output is not None and _native_finish_output_is_protocol_invalid(output):
            continue
        valid.add(item.call_id)
    return valid


def _check_native_evidence_observation(
    *,
    manifest_path: Path,
    manifest: Mapping[str, object],
    transcript: NativeTranscript,
) -> HotPathCheck:
    finish_call_count = sum(1 for item in transcript.items if item.kind == "finish_call")
    observation_ref = str(manifest.get("native_evidence_observation_ref") or "").strip()
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    observation_metrics = (
        metrics.get("native_evidence_observation")
        if isinstance(metrics.get("native_evidence_observation"), dict)
        else {}
    )
    if not finish_call_count and not observation_ref:
        return _check(
            "native_evidence_observation",
            True,
            "no finish claim requires native evidence observation artifact",
            {"finish_call_count": 0, "native_evidence_observation_ref": ""},
        )
    observation_path = (manifest_path.parent / observation_ref).resolve(strict=False) if observation_ref else manifest_path.parent / ""
    loaded_payload = _load_json(observation_path) if observation_ref and observation_path.is_file() else {}
    payload = loaded_payload if isinstance(loaded_payload, dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    claim_count = _int_or_default(summary.get("finish_claim_count"), default=-1)
    known_ref_count = _int_or_default(summary.get("known_tool_evidence_ref_count"), default=-1)
    unresolved_count = _int_or_default(summary.get("unresolved_cited_evidence_ref_count"), default=-1)
    expected_sha = str(manifest.get("native_evidence_observation_sha256") or "").strip()
    metrics_sha = str(observation_metrics.get("artifact_sha256") or "").strip()
    actual_sha = _file_sha256(observation_path) if observation_path.is_file() else ""
    expected_transcript_hash = native_transcript_hash(transcript)
    checks = {
        "ref_present": bool(observation_ref),
        "path_exists": observation_path.is_file(),
        "manifest_sha_matches": bool(expected_sha) and expected_sha == actual_sha,
        "manifest_metrics_sha_matches": bool(metrics_sha) and metrics_sha == actual_sha,
        "source_of_truth": payload.get("source_of_truth") == "response_transcript.json",
        "transcript_hash_matches": payload.get("transcript_hash") == expected_transcript_hash,
        "finish_claim_count_matches": claim_count == finish_call_count,
        "known_ref_count_available": known_ref_count >= 0,
        "unresolved_count_available": unresolved_count >= 0,
        "manifest_metrics_present": bool(observation_metrics),
    }
    ok = all(checks.values())
    return _check(
        "native_evidence_observation",
        ok,
        "native evidence observation links finish claims, known tool evidence refs, and resolver blockers"
        if ok
        else "native evidence observation artifact is missing or not aligned with transcript",
        {
            **checks,
            "native_evidence_observation_ref": observation_ref,
            "native_evidence_observation_sha256": expected_sha,
            "native_evidence_observation_actual_sha256": actual_sha,
            "expected_transcript_hash": expected_transcript_hash,
            "observed_transcript_hash": payload.get("transcript_hash"),
            "finish_call_count": finish_call_count,
            "summary": summary,
            "manifest_metrics": observation_metrics,
        },
    )


def _native_finish_output_is_protocol_invalid(output: NativeTranscriptItem) -> bool:
    if output.kind != "finish_output" or output.status != "invalid" or not output.is_error:
        return False
    text = str(output.output_text_or_ref or "").casefold()
    return any(
        marker in text
        for marker in (
            "invalid json arguments",
            "finish argument",
            "finish arguments contain unsupported keys",
            "must be a string",
            "must be a boolean",
            "must be a string or list of strings",
            "protocol_error",
        )
    )


def _native_provider_requests(*, artifact_path: Path, manifest_path: Path) -> tuple[dict[str, object], ...]:
    for candidate in (
        manifest_path.parent / "native-provider-requests.json",
        artifact_path / "native-provider-requests.json",
        artifact_path / "implement_v2" / "native-provider-requests.json",
    ):
        if not candidate.is_file():
            continue
        data = _load_json(candidate)
        if not isinstance(data, dict):
            continue
        requests = data.get("requests")
        if isinstance(requests, list):
            return tuple(dict(item) for item in requests if isinstance(item, dict))
    return ()


def _native_request_compact_digest(request: Mapping[str, object]) -> dict[str, object]:
    payload = _native_request_task_payload(request)
    digest = payload.get("compact_sidecar_digest")
    return dict(digest) if isinstance(digest, Mapping) else {}


def _native_request_task_contract(request: Mapping[str, object]) -> dict[str, object]:
    payload = _native_request_task_payload(request)
    task_contract = payload.get("task_contract")
    return dict(task_contract) if isinstance(task_contract, Mapping) else {}


def _native_request_task_payload(request: Mapping[str, object]) -> dict[str, object]:
    input_items = _native_request_input_items(request)
    if not isinstance(input_items, list):
        return {}
    for item in input_items:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for chunk in content:
            if not isinstance(chunk, Mapping):
                continue
            if str(chunk.get("type") or "") != "input_text":
                continue
            text = str(chunk.get("text") or "").strip()
            if not text:
                continue
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return dict(decoded)
    return {}


def _native_request_transcript(
    request: Mapping[str, object],
    *,
    fallback_transcript: NativeTranscript,
) -> NativeTranscript:
    window = request.get("transcript_window")
    if isinstance(window, list):
        raw_items = window
    else:
        raw_items = list(fallback_transcript.items[: _nonnegative_int(request.get("input_item_count"))])
    items = tuple(
        item if isinstance(item, NativeTranscriptItem) else _native_transcript_item_from_mapping(item)
        for item in raw_items
        if isinstance(item, (NativeTranscriptItem, Mapping))
    )
    lane_attempt_id = str(request.get("lane_attempt_id") or fallback_transcript.lane_attempt_id)
    provider = _request_transcript_provider(request, fallback_transcript=fallback_transcript)
    model = str(request.get("model") or fallback_transcript.model)
    return NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        model=model,
        items=items,
    )


def _native_request_input_items(request: Mapping[str, object]) -> list[dict[str, object]]:
    input_items = request.get("input_items")
    if isinstance(input_items, list):
        return [dict(item) for item in input_items if isinstance(item, Mapping)]
    request_body = request.get("request_body")
    if isinstance(request_body, Mapping):
        body_input = request_body.get("input")
        if isinstance(body_input, list):
            return [dict(item) for item in body_input if isinstance(item, Mapping)]
    return []


def _native_request_instructions(request: Mapping[str, object]) -> str:
    value = request.get("instructions")
    if isinstance(value, str):
        return value
    request_body = request.get("request_body")
    if isinstance(request_body, Mapping):
        return str(request_body.get("instructions") or "")
    return ""


def _request_transcript_provider(
    request: Mapping[str, object],
    *,
    fallback_transcript: NativeTranscript,
) -> str:
    transport = str(request.get("transport_kind") or "").strip()
    if transport == "fake_native":
        return "fake_native"
    if transport == "provider_native":
        # `_compact_sidecar_digest_for_request` intentionally normalizes live
        # provider-native requests to the codex model backend identity even
        # when the transport adapter records provider="openai".
        return "codex"
    explicit = str(request.get("provider") or "").strip()
    if explicit:
        return explicit
    return fallback_transcript.provider


def _native_request_allows_transition_contract(
    task_payload: Mapping[str, object],
    digest: Mapping[str, object],
) -> bool:
    values = [
        task_payload.get("workframe_variant"),
        task_payload.get("native_projection_variant"),
        digest.get("workframe_variant"),
        _safe_mapping(digest.get("workframe_projection")).get("variant"),
    ]
    lane_config = task_payload.get("lane_config")
    if isinstance(lane_config, Mapping):
        values.append(lane_config.get("workframe_variant"))
    return any(str(value or "").strip() == "transition_contract" for value in values)


def _native_imperative_hint_leaks(projection: Mapping[str, object]) -> list[str]:
    hints = projection.get("attention_hints")
    if not isinstance(hints, list):
        return []
    forbidden = re.compile(r"\b(apply_patch|write_file|edit_file|run_command|read_file|search_text)\b")
    leaks: list[str] = []
    for hint in hints:
        text = str(hint or "").strip()
        if not text:
            continue
        if forbidden.search(text) or re.search(r"[\w./-]+\.(py|js|ts|c|h|rs|go|java|rb|php|sh)\b", text):
            leaks.append(text[:300])
    return leaks


def _load_jsonl_objects(path: Path) -> tuple[list[dict[str, object]], str]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception as exc:
        return [], str(exc)
    return [dict(row) for row in rows if isinstance(row, dict)], ""


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _native_search_text_match_count(text: object) -> int:
    match = re.search(r"\bmatches=(\d+)\b", str(text or ""))
    if not match:
        return 0
    try:
        return max(0, int(match.group(1)))
    except ValueError:
        return 0


def _native_next_turn_index(items: Iterable[NativeTranscriptItem]) -> int:
    max_turn = 0
    for item in items:
        match = re.search(r"(\d+)$", item.turn_id or "")
        if match:
            max_turn = max(max_turn, int(match.group(1)))
    return max_turn + 1 if max_turn else len({item.turn_id for item in items if item.turn_id}) + 1


def _native_transcript_metrics(transcript: NativeTranscript) -> dict[str, object]:
    pairing = validate_native_transcript_pairing(transcript)
    return {
        "transcript_hash": native_transcript_hash(transcript),
        "item_count": len(transcript.items),
        "pairing": pairing.as_dict(),
        "function_call_arguments": native_function_call_argument_metrics(transcript),
    }


def _native_generation_metrics(transcript: NativeTranscript) -> dict[str, object]:
    return native_function_call_argument_metrics(transcript)


def _check_native_generation_observation(transcript: NativeTranscript) -> HotPathCheck:
    metrics = _native_generation_metrics(transcript)
    first_write = _safe_mapping(metrics.get("first_write_call"))
    max_call = _safe_mapping(metrics.get("max_argument_call"))
    suspected = bool(metrics.get("large_write_generation_suspected"))
    message = (
        "large write function-call payload observed; model generation may dominate wall time"
        if suspected
        else "native function-call argument sizes are observable"
    )
    return _check(
        "native_generation_observation",
        True,
        message,
        {
            "large_argument_threshold_chars": metrics.get("large_argument_threshold_chars"),
            "total_argument_chars": metrics.get("total_argument_chars"),
            "max_argument_chars": metrics.get("max_argument_chars"),
            "max_argument_tool_name": max_call.get("tool_name") or "",
            "max_argument_call_id": max_call.get("call_id") or "",
            "max_argument_turn_id": max_call.get("turn_id") or "",
            "large_argument_count": metrics.get("large_argument_count"),
            "write_call_count": metrics.get("write_call_count"),
            "first_write_argument_chars": metrics.get("first_write_argument_chars"),
            "first_write_content_lines_count": first_write.get("content_lines_count") or 0,
            "first_write_tool_name": first_write.get("tool_name") or "",
            "first_write_call_id": first_write.get("call_id") or "",
            "large_write_argument_count": metrics.get("large_write_argument_count"),
            "large_write_generation_suspected": suspected,
        },
    )


def _native_manifest_transport_is_provider_native(manifest: Mapping[str, object]) -> bool:
    metrics = _safe_mapping(manifest.get("metrics"))
    transport_kind = str(manifest.get("transport_kind") or metrics.get("transport_kind") or "")
    native_transport_kind = str(manifest.get("native_transport_kind") or metrics.get("native_transport_kind") or "")
    if transport_kind in {"legacy_model_json", "model_json", "provider_native_unavailable"}:
        return False
    return transport_kind == "provider_native" or native_transport_kind == "provider_native"


def resolve_implement_v2_history_path(artifact: Path, manifest_path: Path) -> Path:
    raw = artifact.expanduser()
    candidates = (
        manifest_path.parent / "history.json",
        raw / "implement_v2" / "history.json",
        raw / "history.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(strict=False)
    search_root = raw if raw.exists() else manifest_path.parent
    recursive = sorted(search_root.rglob("implement_v2/history.json")) if search_root.is_dir() else []
    if recursive:
        return recursive[0].resolve(strict=False)
    raise FileNotFoundError(f"no implement_v2 history.json for artifact: {artifact}")


def _load_manifest_json(path: Path) -> dict[str, object]:
    data = _load_json(path)
    if isinstance(data, dict):
        return dict(data)
    if isinstance(data, list):
        for item in reversed(data):
            if isinstance(item, dict):
                return dict(item)
    raise ValueError(f"expected implement_v2 proof manifest object: {path}")


def _load_baseline_json(path: object | None) -> dict[str, object]:
    if path is None or str(path).strip() == "":
        return {}
    baseline_path = Path(str(path)).expanduser().resolve(strict=False)
    if not baseline_path.is_file():
        raise FileNotFoundError(f"hot-path baseline JSON not found: {baseline_path}")
    data = _load_json(baseline_path)
    if not isinstance(data, dict):
        raise ValueError(f"expected hot-path baseline JSON object: {baseline_path}")
    return dict(data)


def _load_history_json(path: Path) -> list[dict[str, object]]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"expected implement_v2 history array: {path}")
    return [dict(item) for item in data if isinstance(item, dict)]


def _load_workframe_bundle(
    *,
    artifact_path: Path,
    manifest_path: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    bundle_dir = _resolve_workframe_bundle_dir(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    if bundle_dir is None:
        return {
            "bundle_dir": "",
            "missing": True,
            "missing_files": [
                "reducer_inputs.json",
                "reducer_output.workframe.json",
                "invariant_report.json",
                "prompt_visible_workframe.json",
                "prompt_render_inventory.json",
            ],
        }
    files = {
        "reducer_inputs": bundle_dir / "reducer_inputs.json",
        "reducer_output": bundle_dir / "reducer_output.workframe.json",
        "invariant_report": bundle_dir / "invariant_report.json",
        "prompt_visible_workframe": bundle_dir / "prompt_visible_workframe.json",
        "prompt_render_inventory": bundle_dir / "prompt_render_inventory.json",
        "workframe_cursor": bundle_dir / "workframe_cursor.json",
        "reentry_fixture": bundle_dir / "reentry_fixture.json",
    }
    loaded: dict[str, object] = {"bundle_dir": str(bundle_dir), "missing": False, "files": {key: str(path) for key, path in files.items()}}
    missing: list[str] = []
    for key, path in files.items():
        if not path.is_file():
            if key in {"workframe_cursor", "reentry_fixture"}:
                continue
            missing.append(path.name)
            continue
        loaded[key] = _load_json(path)
    loaded["missing_files"] = missing
    return loaded


def _resolve_workframe_bundle_dir(
    *,
    artifact_path: Path,
    manifest_path: Path,
    manifest: dict[str, object],
) -> Path | None:
    workframe_metrics = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("workframe"))
    bundle_root = str(workframe_metrics.get("bundle_root") or "").strip()
    if bundle_root:
        candidate = (manifest_path.parent / bundle_root).resolve(strict=False)
        return candidate if candidate.is_dir() else candidate
    if (artifact_path / "reducer_inputs.json").is_file():
        return artifact_path.resolve(strict=False)
    if (manifest_path.parent / "reducer_inputs.json").is_file():
        return manifest_path.parent.resolve(strict=False)
    roots = [
        manifest_path.parent / "workframes",
        artifact_path / "implement_v2" / "workframes",
        artifact_path / "workframes",
    ]
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(path for path in root.iterdir() if (path / "reducer_inputs.json").is_file())
    if candidates:
        return sorted(candidates, key=lambda path: path.name)[-1].resolve(strict=False)
    return None


def _workframe_inputs_from_mapping(value: object) -> WorkFrameInputs | None:
    data = _safe_mapping(value)
    raw = _safe_mapping(data.get("workframe_inputs")) or data
    if not raw:
        return None
    return WorkFrameInputs(
        attempt_id=str(raw.get("attempt_id") or ""),
        turn_id=str(raw.get("turn_id") or ""),
        task_id=str(raw.get("task_id") or ""),
        objective=str(raw.get("objective") or ""),
        success_contract_ref=str(raw.get("success_contract_ref") or ""),
        constraints=tuple(str(item) for item in raw.get("constraints") or () if str(item)),
        sidecar_events=tuple(dict(item) for item in raw.get("sidecar_events") or () if isinstance(item, dict)),
        prompt_inventory=tuple(dict(item) for item in raw.get("prompt_inventory") or () if isinstance(item, dict)),
        baseline_metrics=_safe_mapping(raw.get("baseline_metrics")),
        previous_workframe_hash=str(raw.get("previous_workframe_hash") or ""),
        workspace_root=str(raw.get("workspace_root") or ""),
        artifact_root=str(raw.get("artifact_root") or ""),
        schema_version=_nonnegative_int(raw.get("schema_version")) or 1,
    )


def _common_workframe_inputs_from_mapping(value: object) -> CommonWorkFrameInputs | None:
    data = _safe_mapping(value)
    inputs = _workframe_inputs_from_mapping(value)
    if inputs is None:
        return None
    raw = _safe_mapping(data.get("common_workframe_inputs"))
    if not raw:
        return common_workframe_inputs_from_workframe_inputs(inputs)
    return CommonWorkFrameInputs(
        current_workframe_inputs=inputs,
        attempt=_safe_mapping(raw.get("attempt")),
        transcript=_safe_mapping(raw.get("transcript")),
        tool_registry=_safe_mapping(raw.get("tool_registry")),
        sidecars=_safe_mapping(raw.get("sidecars")),
        indexes=_safe_mapping(raw.get("indexes")),
        replay=_safe_mapping(raw.get("replay")),
        migration=_safe_mapping(raw.get("migration")),
        schema_version=_nonnegative_int(raw.get("schema_version")) or 1,
    )


def _workframe_bundle_prompt_inventory(bundle: dict[str, object]) -> list[dict[str, object]]:
    inventory = _safe_mapping(bundle.get("prompt_render_inventory"))
    sections = inventory.get("sections")
    return [dict(item) for item in sections if isinstance(item, dict)] if isinstance(sections, list) else []


def _load_micro_next_action_fixture(path: Path) -> dict[str, object]:
    if not str(path):
        raise ValueError("micro next-action fixture is required")
    data = _load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"expected micro next-action JSON object: {path}")
    return dict(data)


def _load_or_refresh_micro_next_action_fixture(
    *,
    artifact_path: Path,
    manifest_path: Path,
    history_path: Path,
    manifest: dict[str, object],
    history: list[dict[str, object]],
    workframe_bundle: dict[str, object],
    micro_read_path: Path,
    micro_write_path: Path,
    refresh_micro_next_action: bool,
    auth_path: object | None,
    model_backend: str,
    model: str,
    base_url: str,
    model_timeout: float,
    expected_categories: tuple[str, ...],
    micro_model_callable: Callable[[str], dict[str, object]] | None,
) -> tuple[dict[str, object], Path, dict[str, object]]:
    context = _micro_next_action_context(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        history_path=history_path,
        manifest=manifest,
        history=history,
        workframe_bundle=workframe_bundle,
        expected_categories=expected_categories,
        model_backend=model_backend,
        model=model,
        base_url=base_url,
    )
    if micro_read_path.is_file() and not refresh_micro_next_action:
        fixture = _load_micro_next_action_fixture(micro_read_path)
        if _micro_fixture_matches_context(fixture, context):
            return fixture, micro_read_path, {"mode": "reused", "reason": "fixture_hash_match"}

    prompt = str(context["prompt"])
    if micro_model_callable is None:
        auth = load_model_auth(model_backend, auth_path)
        payload = call_model_json(model_backend, auth, prompt, model, base_url, model_timeout)
    else:
        payload = micro_model_callable(prompt)
    if not isinstance(payload, dict):
        raise ValueError("micro next-action model response must be a JSON object")
    fixture = _build_micro_next_action_fixture(
        payload=payload,
        context=context,
        model_backend=model_backend,
        model=model,
        expected_categories=expected_categories,
    )
    micro_write_path.parent.mkdir(parents=True, exist_ok=True)
    micro_write_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return fixture, micro_write_path, {
        "mode": "refreshed",
        "reason": "forced" if refresh_micro_next_action else "fixture_missing_or_stale",
    }


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_micro_fixture_paths(
    *,
    manifest_path: Path,
    micro_next_action: object | None,
    micro_next_action_output: object | None,
) -> tuple[Path, Path]:
    default_path = (manifest_path.parent / "hot-path-micro-next-action.json").resolve(strict=False)
    read_path = Path(str(micro_next_action)).expanduser().resolve(strict=False) if micro_next_action else default_path
    write_path = (
        Path(str(micro_next_action_output)).expanduser().resolve(strict=False)
        if micro_next_action_output
        else read_path
    )
    return read_path, write_path


def _micro_next_action_context(
    *,
    artifact_path: Path,
    manifest_path: Path,
    history_path: Path,
    manifest: dict[str, object],
    history: list[dict[str, object]],
    workframe_bundle: dict[str, object],
    expected_categories: tuple[str, ...],
    model_backend: str,
    model: str,
    base_url: str,
) -> dict[str, object]:
    projected_history = _render_prompt_history_json(history)
    manifest_digest = _json_sha256(manifest)
    history_digest = _json_sha256(history)
    projected_history_digest = _text_sha256(projected_history)
    category_text = ", ".join(_expected_micro_categories(expected_categories))
    effective_model = model or model_backend_default_model(model_backend)
    effective_base_url = base_url or model_backend_default_base_url(model_backend)
    hot_path = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("hot_path_projection"))
    sidecar = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("resident_sidecar_state"))
    workframe_output = _safe_mapping(workframe_bundle.get("reducer_output"))
    prompt_visible_workframe = _safe_mapping(workframe_bundle.get("prompt_visible_workframe"))
    workframe_output_digest = _json_sha256(workframe_output)
    prompt_visible_digest = _json_sha256(prompt_visible_workframe)
    workframe_trace = _safe_mapping(workframe_output.get("trace"))
    prompt = _build_micro_next_action_prompt(
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        history_path=history_path,
        projected_history=projected_history,
        expected_categories=expected_categories,
        hot_path=hot_path,
        sidecar=sidecar,
        workframe_output=workframe_output,
        prompt_visible_workframe=prompt_visible_workframe,
    )
    prompt_digest = _text_sha256(prompt)
    context_hash = _json_sha256(
        {
            "manifest_sha256": manifest_digest,
            "history_sha256": history_digest,
            "projected_history_sha256": projected_history_digest,
            "prompt_sha256": prompt_digest,
            "expected_categories": list(_expected_micro_categories(expected_categories)),
            "workframe_output_sha256": workframe_output_digest,
            "prompt_visible_workframe_sha256": prompt_visible_digest,
            "workframe_input_hash": workframe_trace.get("input_hash"),
            "workframe_output_hash": workframe_trace.get("output_hash"),
            "model_backend": model_backend,
            "model": effective_model,
            "base_url": effective_base_url,
        }
    )
    return {
        "artifact_path": str(artifact_path),
        "manifest_path": str(manifest_path),
        "history_path": str(history_path),
        "manifest_sha256": manifest_digest,
        "history_sha256": history_digest,
        "projected_history_sha256": projected_history_digest,
        "workframe_output_sha256": workframe_output_digest,
        "prompt_visible_workframe_sha256": prompt_visible_digest,
        "workframe_input_hash": workframe_trace.get("input_hash"),
        "workframe_output_hash": workframe_trace.get("output_hash"),
        "prompt_sha256": prompt_digest,
        "context_hash": context_hash,
        "expected_categories": list(_expected_micro_categories(expected_categories)),
        "category_text": category_text,
        "model_backend": model_backend,
        "model": effective_model,
        "base_url": effective_base_url,
        "prompt": prompt,
    }


def _build_micro_next_action_prompt(
    *,
    artifact_path: Path,
    manifest_path: Path,
    history_path: Path,
    projected_history: str,
    expected_categories: tuple[str, ...],
    hot_path: dict[str, object],
    sidecar: dict[str, object],
    workframe_output: dict[str, object],
    prompt_visible_workframe: dict[str, object],
) -> str:
    allowed = ", ".join(category for category in NEXT_ACTION_CATEGORIES if category != "invalid")
    expected = ", ".join(_expected_micro_categories(expected_categories)) or allowed
    metrics = {
        "hot_path_phase": hot_path.get("phase"),
        "normal_full_prompt_bytes": hot_path.get("normal_full_prompt_bytes"),
        "normal_full_prompt_bytes_total": hot_path.get("normal_full_prompt_bytes_total"),
        "provider_visible_tool_result_bytes": hot_path.get("provider_visible_tool_result_bytes"),
        "sidecar_total_bytes": sidecar.get("total_bytes"),
        "sidecar_per_turn_growth_bytes": sidecar.get("per_turn_growth_bytes"),
    }
    return "\n".join(
        [
            "You are running a micro next-action check for mew implement_v2.",
            "Classify the single best next action category from the saved projected history.",
            "Do not solve the task. Do not emit a command. Return JSON only.",
            "",
            "Allowed categories:",
            allowed,
            "",
            "Expected passing categories for this check:",
            expected,
            "",
            "Output schema:",
            json.dumps(
                {
                    "category": "patch/edit | run_verifier | inspect_latest_failure | cheap_probe | finish_with_evidence | blocked | invalid",
                    "reason": "short reason grounded in the projected history",
                    "tool_name": "optional tool family",
                    "confidence": "low | medium | high",
                },
                ensure_ascii=False,
            ),
            "",
            "Artifacts:",
            json.dumps(
                {
                    "artifact_path": str(artifact_path),
                    "manifest_path": str(manifest_path),
                    "history_path": str(history_path),
                    "metrics": metrics,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "",
            "Current WorkFrame JSON:",
            _clip_text(json.dumps(prompt_visible_workframe or {"workframe": workframe_output}, ensure_ascii=False, sort_keys=True), 12000),
            "",
            "Projected implement_v2 history JSON:",
            _clip_text(projected_history, 24000),
        ]
    )


def _micro_fixture_matches_context(fixture: dict[str, object], context: dict[str, object]) -> bool:
    valid_for = _safe_mapping(fixture.get("valid_for"))
    return (
        fixture.get("schema_version") == HOT_PATH_FASTCHECK_SCHEMA_VERSION
        and str(valid_for.get("context_hash") or "") == str(context.get("context_hash") or "")
        and str(valid_for.get("prompt_sha256") or "") == str(context.get("prompt_sha256") or "")
    )


def _build_micro_next_action_fixture(
    *,
    payload: dict[str, object],
    context: dict[str, object],
    model_backend: str,
    model: str,
    expected_categories: tuple[str, ...],
) -> dict[str, object]:
    category = _micro_next_action_category(payload)
    effective_model = model or model_backend_default_model(model_backend)
    return {
        "schema_version": HOT_PATH_FASTCHECK_SCHEMA_VERSION,
        "source": "live_llm_micro_next_action",
        "backend": model_backend,
        "model": effective_model,
        "category": category,
        "expected_categories": list(_expected_micro_categories(expected_categories)),
        "reason": str(payload.get("reason") or payload.get("summary") or "").strip(),
        "valid_for": {
            "context_hash": context.get("context_hash"),
            "manifest_sha256": context.get("manifest_sha256"),
            "history_sha256": context.get("history_sha256"),
            "projected_history_sha256": context.get("projected_history_sha256"),
            "workframe_output_sha256": context.get("workframe_output_sha256"),
            "prompt_visible_workframe_sha256": context.get("prompt_visible_workframe_sha256"),
            "workframe_input_hash": context.get("workframe_input_hash"),
            "workframe_output_hash": context.get("workframe_output_hash"),
            "prompt_sha256": context.get("prompt_sha256"),
            "model_backend": model_backend,
            "model": effective_model,
            "base_url": context.get("base_url"),
        },
        "model_output": payload,
    }


def _format_micro_refresh_line(value: object) -> str:
    if not isinstance(value, dict):
        return "(unknown)"
    mode = value.get("mode") or "(unknown)"
    reason = value.get("reason") or ""
    return f"{mode} ({reason})" if reason else str(mode)


def _json_sha256(value: object) -> str:
    return _text_sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clip_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    head = max(0, limit // 2)
    tail = max(0, limit - head)
    return value[:head] + "\n...[truncated for micro next-action check]...\n" + value[-tail:]


def _check_manifest_lane(manifest: dict[str, object]) -> HotPathCheck:
    lane = str(manifest.get("lane") or "")
    return _check(
        "manifest_lane",
        lane == "implement_v2",
        f"lane={lane or '(missing)'}",
        {"lane": lane},
    )


def _check_hot_path_metrics(manifest: dict[str, object]) -> HotPathCheck:
    metrics = _safe_mapping(manifest.get("metrics"))
    hot_path = _safe_mapping(metrics.get("hot_path_projection"))
    workframe = _safe_mapping(metrics.get("workframe"))
    phase = str(hot_path.get("phase") or "")
    ok = bool(hot_path) and phase.startswith("m6_24_workframe_redesign_phase_")
    return _check(
        "hot_path_projection_metrics",
        ok,
        "hot_path_projection metrics present" if ok else "missing or stale hot_path_projection metrics",
        {
            "phase": phase,
            "normal_full_prompt_bytes": hot_path.get("normal_full_prompt_bytes"),
            "workframe_phase": workframe.get("phase"),
            "workframe_output_hash": workframe.get("output_hash"),
        },
    )


def _check_prompt_leaks(
    manifest: dict[str, object],
    *,
    workframe_bundle: dict[str, object],
    max_active_todo_bytes: int,
) -> HotPathCheck:
    hot_path = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("hot_path_projection"))
    bundle_inventory = _workframe_bundle_prompt_inventory(workframe_bundle)
    inventory = bundle_inventory or hot_path.get("normal_section_inventory")
    ordinary = (
        [dict(item) for item in inventory if isinstance(item, dict) and item.get("visibility") == "ordinary"]
        if isinstance(inventory, list)
        else []
    )
    disallowed = []
    active_todo_bytes = 0
    workframe_sections = []
    for section in ordinary:
        section_id = str(section.get("id") or "")
        lowered = section_id.lower()
        if any(
            token in lowered
            for token in (
                "frontier_state_update",
                "active_work_todo",
                "hard_runtime_frontier",
                "repair_history",
                "proof_manifest",
                "oracle_bundle",
                "typed_evidence_object",
                "execution_contract_object",
            )
        ):
            disallowed.append(section_id)
        if section_id == "implement_v2_workframe":
            workframe_sections.append(section)
        if section_id == "implement_v2_active_work_todo":
            active_todo_bytes = _nonnegative_int(section.get("bytes"))
    prompt_visible = _safe_mapping(workframe_bundle.get("prompt_visible_workframe"))
    visible_text = json.dumps(prompt_visible, ensure_ascii=False, sort_keys=True)
    visible_leaks = [
        token
        for token in (
            "frontier_state_update",
            "implement_v2_active_work_todo",
            "lane_hard_runtime_frontier",
            "proof_manifest",
            "oracle_bundle",
            "typed_evidence_object",
            "execution_contract_object",
            '"execution_contract"',
            '"oracle_bundle"',
        )
        if token in visible_text
    ]
    ok = (
        len(workframe_sections) == 1
        and not disallowed
        and not visible_leaks
        and active_todo_bytes <= max_active_todo_bytes
    )
    return _check(
        "prompt_leak_contract",
        ok,
        "normal prompt exposes exactly one WorkFrame and no legacy projection"
        if ok
        else "normal prompt exposes disallowed, duplicated, or oversized hot-path state",
        {
            "disallowed_sections": disallowed,
            "workframe_section_count": len(workframe_sections),
            "visible_leaks": visible_leaks,
            "active_work_todo_bytes": active_todo_bytes,
            "max_active_todo_bytes": max_active_todo_bytes,
        },
    )


def _check_sidecar_metrics(
    manifest: dict[str, object],
    *,
    baseline: dict[str, object],
    max_total_bytes: int,
    max_per_turn_growth_bytes: int,
) -> HotPathCheck:
    sidecar = _safe_mapping(_safe_mapping(manifest.get("metrics")).get("resident_sidecar_state"))
    families = _safe_mapping(sidecar.get("families"))
    total_bytes = _nonnegative_int(sidecar.get("total_bytes"))
    per_turn_growth_bytes = _nonnegative_float(sidecar.get("per_turn_growth_bytes"))
    cap_source = "absolute"
    baseline_sidecar = _baseline_sidecar_metrics(baseline)
    total_band = ""
    per_turn_growth_band = ""
    baseline_missing = bool(baseline) and not baseline_sidecar
    if baseline_sidecar:
        cap_source = "phase0_baseline"
        baseline_total_bytes = _nonnegative_int(baseline_sidecar.get("total_bytes"))
        baseline_growth_bytes = _nonnegative_float(baseline_sidecar.get("per_turn_growth_bytes"))
        max_total_bytes = max(1, int(round(baseline_total_bytes * PHASE0_YELLOW_TOTAL_RATIO)))
        max_per_turn_growth_bytes = max(1, int(round(baseline_growth_bytes * PHASE0_RED_PER_TURN_GROWTH_RATIO)))
        total_band = _ratio_band(
            total_bytes,
            baseline_total_bytes,
            green=PHASE0_GREEN_TOTAL_RATIO,
            yellow=PHASE0_YELLOW_TOTAL_RATIO,
        )
        per_turn_growth_band = _ratio_band(
            per_turn_growth_bytes,
            baseline_growth_bytes,
            green=1.0,
            yellow=PHASE0_RED_PER_TURN_GROWTH_RATIO,
        )
    ok = (
        sidecar.get("surface") == "resident_sidecar_state"
        and not baseline_missing
        and 0 < total_bytes <= max_total_bytes
        and 0 < per_turn_growth_bytes <= max_per_turn_growth_bytes
        and bool(families)
    )
    return _check(
        "resident_sidecar_metrics",
        ok,
        "resident sidecar metrics within cap" if ok else "resident sidecar metrics missing, empty, or over cap",
        {
            "surface": sidecar.get("surface"),
            "total_bytes": total_bytes,
            "max_total_bytes": max_total_bytes,
            "per_turn_growth_bytes": per_turn_growth_bytes,
            "max_per_turn_growth_bytes": max_per_turn_growth_bytes,
            "families": sorted(str(key) for key in families),
            "cap_source": cap_source,
            "baseline_total_bytes": _nonnegative_int(baseline_sidecar.get("total_bytes")) if baseline_sidecar else 0,
            "baseline_per_turn_growth_bytes": (
                _nonnegative_float(baseline_sidecar.get("per_turn_growth_bytes")) if baseline_sidecar else 0.0
            ),
            "total_band": total_band,
            "per_turn_growth_band": per_turn_growth_band,
            "baseline_missing": baseline_missing,
        },
    )


def _check_workframe_replay(bundle: dict[str, object], manifest: dict[str, object] | None = None) -> HotPathCheck:
    missing = [str(item) for item in bundle.get("missing_files") or () if str(item)]
    if bundle.get("missing") or missing:
        return _check(
            "workframe_replay",
            False,
            "missing WorkFrame replay bundle",
            {"bundle_dir": bundle.get("bundle_dir"), "missing_files": missing},
        )
    inputs = _workframe_inputs_from_mapping(bundle.get("reducer_inputs"))
    if inputs is None:
        return _check("workframe_replay", False, "invalid reducer_inputs.json", {"bundle_dir": bundle.get("bundle_dir")})
    stored_inputs = _safe_mapping(bundle.get("reducer_inputs"))
    stored_cursor = _safe_mapping(bundle.get("workframe_cursor"))
    workframe_variant = str(
        stored_inputs.get("workframe_variant")
        or _safe_mapping(_safe_mapping((manifest or {}).get("metrics")).get("workframe")).get("variant")
        or "current"
    )
    stored_canonical = _safe_mapping(stored_inputs.get("canonical"))
    common_inputs = _common_workframe_inputs_from_mapping(stored_inputs)
    if common_inputs is not None and stored_inputs.get("common_workframe_inputs_schema_version"):
        canonical = canonicalize_common_workframe_inputs(common_inputs)
        projection = project_workframe_with_variant(common_inputs, variant=workframe_variant)
        workframe = projection.workframe
        report = projection.invariant_report
        shared_substrate_hash = projection.shared_substrate_hash
        projection_hash = projection.projection_hash
    else:
        canonical = canonicalize_workframe_inputs(inputs)
        workframe, report = reduce_workframe_with_variant(inputs, variant=workframe_variant)
        shared_substrate_hash = ""
        projection_hash = ""
    stored_output = _safe_mapping(bundle.get("reducer_output"))
    recomputed_output = workframe.as_dict()
    stored_report = _safe_mapping(bundle.get("invariant_report"))
    manifest_workframe = _safe_mapping(_safe_mapping((manifest or {}).get("metrics")).get("workframe"))
    manifest_input_hash = str(manifest_workframe.get("input_hash") or "")
    manifest_output_hash = str(manifest_workframe.get("output_hash") or "")
    stored_shared_substrate_hash = str(stored_inputs.get("shared_substrate_hash") or "")
    cursor_shared_substrate_hash = str(stored_cursor.get("shared_substrate_hash") or "")
    cursor_projection_hash = str(stored_cursor.get("projection_hash") or "")
    shared_hash_matches = not shared_substrate_hash or (
        stored_shared_substrate_hash == shared_substrate_hash
        and cursor_shared_substrate_hash == shared_substrate_hash
    )
    projection_hash_matches = not projection_hash or (
        cursor_projection_hash == projection_hash
    )
    ok = (
        bool(stored_canonical)
        and stored_canonical == canonical
        and stored_output == recomputed_output
        and _safe_mapping(stored_output.get("trace")).get("output_hash") == workframe_output_hash(workframe)
        and bool(manifest_input_hash)
        and bool(manifest_output_hash)
        and manifest_input_hash == workframe.trace.input_hash
        and manifest_output_hash == workframe.trace.output_hash
        and stored_report.get("status") == report.status
        and shared_hash_matches
        and projection_hash_matches
    )
    return _check(
        "workframe_replay",
        ok,
        "saved WorkFrame replay matches reducer" if ok else "saved WorkFrame replay does not match reducer",
        {
            "bundle_dir": bundle.get("bundle_dir"),
            "workframe_variant": workframe_variant,
            "stored_input_hash": _safe_mapping(stored_output.get("trace")).get("input_hash"),
            "recomputed_input_hash": workframe.trace.input_hash,
            "stored_output_hash": _safe_mapping(stored_output.get("trace")).get("output_hash"),
            "recomputed_output_hash": workframe.trace.output_hash,
            "manifest_input_hash": manifest_input_hash,
            "manifest_output_hash": manifest_output_hash,
            "manifest_input_hash_present": bool(manifest_input_hash),
            "manifest_output_hash_present": bool(manifest_output_hash),
            "manifest_input_hash_matches": manifest_input_hash == workframe.trace.input_hash,
            "manifest_output_hash_matches": manifest_output_hash == workframe.trace.output_hash,
            "canonical_present": bool(stored_canonical),
            "canonical_matches": stored_canonical == canonical,
            "output_matches": stored_output == recomputed_output,
            "stored_invariant_status": stored_report.get("status"),
            "recomputed_invariant_status": report.status,
            "stored_shared_substrate_hash": stored_shared_substrate_hash,
            "recomputed_shared_substrate_hash": shared_substrate_hash,
            "cursor_shared_substrate_hash": cursor_shared_substrate_hash,
            "shared_substrate_hash_matches": shared_hash_matches,
            "cursor_projection_hash": cursor_projection_hash,
            "recomputed_projection_hash": projection_hash,
            "projection_hash_matches": projection_hash_matches,
        },
    )


def _check_workframe_invariants(bundle: dict[str, object]) -> HotPathCheck:
    output = _safe_mapping(bundle.get("reducer_output"))
    report = _safe_mapping(bundle.get("invariant_report"))
    serialized_bytes = len(canonical_json(output).encode("utf-8")) if output else 0
    ok = bool(output) and report.get("status") == "pass" and 0 < serialized_bytes <= WORKFRAME_RED_MAX_BYTES
    return _check(
        "workframe_invariants",
        ok,
        "WorkFrame invariants pass" if ok else "WorkFrame invariants fail or frame exceeds cap",
        {
            "status": report.get("status"),
            "failed": report.get("failed") if isinstance(report.get("failed"), list) else [],
            "bytes": serialized_bytes,
            "red_cap": WORKFRAME_RED_MAX_BYTES,
            "current_phase": output.get("current_phase"),
        },
    )


def _check_workframe_evidence_refs(bundle: dict[str, object]) -> HotPathCheck:
    output = _safe_mapping(bundle.get("reducer_output"))
    inputs = _workframe_inputs_from_mapping(bundle.get("reducer_inputs"))
    resolver = _workframe_resolvable_refs(inputs)
    unresolved: list[str] = []
    replay_model_fetchable: list[str] = []
    for ref in _workframe_output_refs(output):
        if ref.startswith("replay:"):
            replay_model_fetchable.append(ref) if _ref_is_model_fetchable(ref) else None
            continue
        if ref not in resolver:
            unresolved.append(ref)
    ok = not unresolved and not replay_model_fetchable
    return _check(
        "workframe_evidence_ref_policy",
        ok,
        "WorkFrame evidence refs resolve to sidecar/typed facts"
        if ok
        else "WorkFrame evidence refs are unresolved or replay-fetchable",
        {
            "unresolved": sorted(set(unresolved)),
            "replay_model_fetchable": sorted(set(replay_model_fetchable)),
            "resolver_count": len(resolver),
        },
    )


def _check_workframe_reentry_stability(bundle: dict[str, object]) -> HotPathCheck:
    fixture = _safe_mapping(bundle.get("reentry_fixture"))
    if not fixture:
        return _check(
            "workframe_reentry_stability",
            True,
            "no reentry fixture present; stability check skipped",
            {"skipped": True},
        )
    before = _safe_mapping(fixture.get("before") or fixture.get("pre_resume"))
    after = _safe_mapping(fixture.get("after") or fixture.get("post_resume"))
    before_projection = _compression_stability_projection(before)
    after_projection = _compression_stability_projection(after)
    semantic_changed = bool(fixture.get("semantic_event_changed"))
    ok = semantic_changed or before_projection == after_projection
    return _check(
        "workframe_reentry_stability",
        ok,
        "reentry preserved WorkFrame safety/navigation state"
        if ok
        else "reentry drifted WorkFrame safety/navigation state without semantic event",
        {
            "semantic_event_changed": semantic_changed,
            "projection_matches": before_projection == after_projection,
            "before": before_projection,
            "after": after_projection,
        },
    )


def _compression_stability_projection(workframe: dict[str, object]) -> dict[str, object]:
    tool_context = _safe_mapping(workframe.get("tool_context"))
    return {
        "required_next": _safe_mapping(workframe.get("required_next")),
        "forbidden_next": workframe.get("forbidden_next") if isinstance(workframe.get("forbidden_next"), list) else [],
        "verifier_state": _safe_mapping(workframe.get("verifier_state")),
        "finish_readiness": _safe_mapping(workframe.get("finish_readiness")),
        "obligations": _safe_mapping(workframe.get("obligations")),
        "tool_context": {
            "active_tool_refs": _list_or_empty(tool_context.get("active_tool_refs")),
            "recommended_tool_refs": _list_or_empty(tool_context.get("recommended_tool_refs")),
            "disabled_tool_refs": _list_or_empty(tool_context.get("disabled_tool_refs")),
            "policy_refs": _list_or_empty(tool_context.get("policy_refs")),
            "fetchable_refs": _list_or_empty(tool_context.get("fetchable_refs")),
            "tool_result_search": _safe_mapping(tool_context.get("tool_result_search")),
            "model_turn_search": _safe_mapping(tool_context.get("model_turn_search")),
        },
    }


def _list_or_empty(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _check_legacy_projection_rejected(history: list[dict[str, object]]) -> HotPathCheck:
    leaked: list[dict[str, object]] = []
    rejected = 0
    for entry in history:
        for value in _walk(entry):
            if not isinstance(value, dict):
                continue
            if "frontier_state_update" in value:
                leaked.append({"turn": entry.get("turn"), "field": "frontier_state_update"})
            if value.get("class") == "legacy_projection_field_rejected":
                rejected += 1
            if value.get("class") == "legacy_projection_field_ignored":
                leaked.append({"turn": entry.get("turn"), "field": "legacy_projection_field_ignored"})
    ok = not leaked
    return _check(
        "legacy_projection_field_rejected",
        ok,
        "no legacy model projection fields reached saved history"
        if ok
        else "legacy model projection fields were ignored or leaked instead of hard-rejected",
        {"leaked": leaked, "rejected_events": rejected},
    )


def _workframe_resolvable_refs(inputs: WorkFrameInputs | None) -> set[str]:
    refs: set[str] = set()
    if inputs is None:
        return refs
    if inputs.success_contract_ref:
        refs.add(inputs.success_contract_ref)
    for event in inputs.sidecar_events:
        refs.update(_resolvable_refs_from_event(event))
    return refs


def _resolvable_refs_from_event(event: dict[str, object]) -> set[str]:
    refs: set[str] = set()
    for value in _walk(event):
        if not isinstance(value, dict):
            continue
        for key in (
            "event_id",
            "event_ref",
            "evidence_ref",
            "evidence_id",
            "command_run_id",
            "typed_evidence_id",
            "id",
            "ref",
            "contract_id",
            "finish_gate_id",
            "oracle_bundle_id",
            "output_ref",
        ):
            ref = str(value.get(key) or "").strip()
            if ref:
                refs.add(ref)
        for key in ("evidence_refs", "required_evidence_refs", "missing_obligations", "required_obligations", "oracle_obligations"):
            refs.update(_refs_from_ref_list(value.get(key)))
        for key in ("execution_contract", "execution_contract_normalized", "finish_gate", "oracle_bundle", "typed_acceptance"):
            refs.update(_refs_from_nested_mapping(value.get(key)))
    return refs


def _refs_from_nested_mapping(value: object) -> set[str]:
    refs: set[str] = set()
    if not isinstance(value, dict):
        return refs
    for key in ("id", "ref", "evidence_id", "contract_id", "finish_gate_id", "oracle_bundle_id"):
        ref = str(value.get(key) or "").strip()
        if ref:
            refs.add(ref)
    for key in ("evidence_refs", "required_evidence_refs", "missing_obligations", "required_obligations", "oracle_obligations"):
        refs.update(_refs_from_ref_list(value.get(key)))
    digest = value.get("digest") if isinstance(value.get("digest"), dict) else {}
    refs.update(_refs_from_ref_list(digest.get("missing_obligations")))
    return refs


def _refs_from_ref_list(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str) and value.strip():
        refs.add(value.strip())
    elif isinstance(value, dict):
        refs.update(_refs_from_nested_mapping(value))
    elif isinstance(value, (list, tuple)):
        for item in value:
            refs.update(_refs_from_ref_list(item))
    return refs


def _workframe_output_refs(output: dict[str, object]) -> set[str]:
    refs: set[str] = set()
    for value in _walk(output):
        if not isinstance(value, dict):
            continue
        for key in ("evidence_refs", "required_evidence_refs", "missing_obligations"):
            raw = value.get(key)
            if isinstance(raw, list):
                refs.update(str(item) for item in raw if str(item))
        for key in ("source_ref", "latest_mutation_ref", "last_strict_verifier_ref", "configured_verifier_ref"):
            ref = str(value.get(key) or "").strip()
            if ref:
                refs.add(ref)
    return refs


def _ref_is_model_fetchable(ref: str) -> bool:
    return ref.startswith(("tool:", "out:", "sidecar:", "ev:", "cmd:", "contract:", "oracle:"))


def _baseline_sidecar_metrics(baseline: dict[str, object]) -> dict[str, object]:
    metrics = _safe_mapping(baseline.get("metrics"))
    sidecar = _safe_mapping(metrics.get("resident_sidecar_state"))
    if sidecar:
        return sidecar
    return _safe_mapping(baseline.get("resident_sidecar_state"))


def _check_latest_actionable_failure_shape(history: list[dict[str, object]]) -> HotPathCheck:
    projected = json.loads(_render_prompt_history_json(history))
    families = _latest_failure_families(projected)
    duplicate_families = sorted(family for family, count in _counts(families).items() if count > 1)
    generic_runtime_failures = _generic_runtime_failure_summaries(projected)
    failure_results = _non_completed_tool_result_count(history)
    ok = not duplicate_families and not generic_runtime_failures and (failure_results == 0 or bool(families))
    return _check(
        "latest_actionable_failure_shape",
        ok,
        "latest actionable failure is projected once per family"
        if ok
        else "latest actionable failure projection missing or duplicated",
        {
            "failure_tool_results": failure_results,
            "latest_failure_families": families,
            "duplicate_families": duplicate_families,
            "generic_runtime_failures": generic_runtime_failures,
        },
    )


def _check_micro_next_action(
    fixture: dict[str, object],
    *,
    expected_categories: tuple[str, ...],
) -> HotPathCheck:
    category = _micro_next_action_category(fixture)
    expected = _expected_micro_categories(expected_categories)
    ok = bool(category) and category != "invalid" and category in expected
    return _check(
        "micro_next_action",
        ok,
        f"micro next-action category={category or '(missing)'} expected={','.join(expected) or '(missing)'}",
        {"category": category, "expected_categories": list(expected)},
    )


def _micro_next_action_category(fixture: dict[str, object]) -> str:
    category = str(fixture.get("category") or "").strip()
    if category:
        return category if category in NEXT_ACTION_CATEGORIES else "invalid"
    output = fixture.get("model_output")
    if not isinstance(output, dict):
        return ""
    calls = output.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        finish = output.get("finish")
        if isinstance(finish, dict):
            outcome = str(finish.get("outcome") or "").strip().lower()
            if outcome in {"completed", "task_complete", "done", "success"}:
                return "finish_with_evidence"
            if outcome in {"blocked", "failed"}:
                return "blocked"
        return "invalid" if finish else ""
    first = calls[0] if isinstance(calls[0], dict) else {}
    tool_name = str(first.get("name") or first.get("tool_name") or "").strip()
    arguments = first.get("arguments") if isinstance(first.get("arguments"), dict) else {}
    if tool_name in {"write_file", "edit_file", "apply_patch"}:
        return "patch/edit"
    if tool_name == "run_tests":
        return "run_verifier"
    if tool_name == "run_command":
        intent = str(arguments.get("command_intent") or "").lower()
        command = str(arguments.get("command") or arguments.get("cmd") or "").lower()
        if "verify" in intent or "test" in intent or "pytest" in command or "node " in command:
            return "run_verifier"
        return "cheap_probe"
    if tool_name in {"read_file", "search_text", "glob", "inspect_dir"}:
        return "cheap_probe"
    return "invalid"


def _expected_micro_categories(expected_categories: Iterable[str]) -> tuple[str, ...]:
    allowed = set(NEXT_ACTION_CATEGORIES) - {"invalid"}
    expected = tuple(
        str(item).strip()
        for item in expected_categories
        if str(item).strip() in allowed
    )
    if expected:
        return expected
    return tuple(category for category in NEXT_ACTION_CATEGORIES if category in allowed)


def _latest_failure_families(projected_history: object) -> list[str]:
    families: list[str] = []
    for value in _walk(projected_history):
        if not isinstance(value, dict):
            continue
        if value.get("replaced_by_later_latest_failure"):
            continue
        latest_failure = value.get("latest_failure")
        if isinstance(latest_failure, dict):
            family = _latest_failure_family(latest_failure, context=value)
            if family:
                families.append(family)
        latest_failures = value.get("latest_failures")
        if isinstance(latest_failures, list):
            for item in latest_failures:
                if isinstance(item, dict):
                    family = _latest_failure_family(item, context=value)
                    if family:
                        families.append(family)
    return families


def _latest_failure_family(latest_failure: dict[str, object], *, context: dict[str, object] | None = None) -> str:
    failure_class = str(latest_failure.get("class") or latest_failure.get("failure_class") or "").strip()
    failure_kind = str(latest_failure.get("kind") or "").strip()
    provider_identity = str(latest_failure.get("provider_family_identity") or "").strip()
    artifact_identity = provider_identity or _latest_failure_artifact_identity(latest_failure, context=context)
    if artifact_identity:
        identity = artifact_identity
    else:
        summary = str(latest_failure.get("summary") or latest_failure.get("required_next_action") or "").strip()
        identity = f"summary:{summary[:120]}" if summary else "unknown"
    return f"{failure_class or 'unknown'}:{failure_kind or 'unknown'}:{identity}"


def _latest_failure_artifact_identity(
    latest_failure: dict[str, object],
    *,
    context: dict[str, object] | None = None,
) -> str:
    for source in (context, latest_failure):
        if not isinstance(source, dict):
            continue
        digest = source.get("execution_evidence_digest")
        if isinstance(digest, dict):
            artifact_misses = digest.get("artifact_miss")
            if isinstance(artifact_misses, list):
                for artifact in artifact_misses:
                    if not isinstance(artifact, dict):
                        continue
                    artifact_id = str(artifact.get("artifact_id") or "").strip()
                    path = str(artifact.get("path") or "").strip()
                    if artifact_id or path:
                        return f"artifact:{artifact_id}:{path}"
        artifact_evidence = source.get("artifact_evidence")
        if isinstance(artifact_evidence, list):
            for artifact in artifact_evidence:
                if not isinstance(artifact, dict):
                    continue
                if artifact.get("status") in {"passed", "completed"} or artifact.get("blocking") is False:
                    continue
                artifact_id = str(artifact.get("artifact_id") or "").strip()
                path = str(artifact.get("path") or "").strip()
                if artifact_id or path:
                    return f"artifact:{artifact_id}:{path}"
    path = str(latest_failure.get("path") or "").strip()
    return f"path:{path}" if path else ""


def _generic_runtime_failure_summaries(projected_history: object) -> list[dict[str, object]]:
    failures: list[dict[str, object]] = []
    for value in _walk(projected_history):
        if not isinstance(value, dict):
            continue
        for latest_failure in _iter_latest_failure_dicts(value):
            failure_class = str(latest_failure.get("class") or latest_failure.get("failure_class") or "").strip()
            summary = str(latest_failure.get("summary") or "").strip().lower()
            if failure_class == "runtime_failure" and _is_generic_runtime_failure_summary(summary):
                failures.append(
                    {
                        "class": failure_class,
                        "kind": str(latest_failure.get("kind") or ""),
                        "summary": str(latest_failure.get("summary") or ""),
                    }
                )
    return failures


def _is_generic_runtime_failure_summary(summary: str) -> bool:
    text = summary.strip().lower()
    return bool(
        text in {"exit code 1", "command failed", "failed", "killed", "interrupted"}
        or re.fullmatch(r"exit code \d+", text)
        or re.fullmatch(r"tool run .* ended with killed", text)
        or re.fullmatch(r"tool run .* ended with interrupted", text)
    )


def _iter_latest_failure_dicts(value: dict[str, object]) -> Iterable[dict[str, object]]:
    latest_failure = value.get("latest_failure")
    if isinstance(latest_failure, dict):
        yield latest_failure
    latest_failures = value.get("latest_failures")
    if isinstance(latest_failures, list):
        for item in latest_failures:
            if isinstance(item, dict):
                yield item


def _non_completed_tool_result_count(history: list[dict[str, object]]) -> int:
    count = 0
    for entry in history:
        results = entry.get("tool_results") if isinstance(entry.get("tool_results"), list) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            status = str(result.get("status") or "").strip()
            if status and status not in {"completed", "yielded", "running"}:
                count += 1
    return count


def _walk(value: object) -> Iterable[object]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child)


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _safe_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _nonnegative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _int_or_default(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _nonnegative_float(value: object) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _ratio_band(value: float, baseline: float, *, green: float, yellow: float) -> str:
    if baseline <= 0:
        return ""
    ratio = value / baseline
    if ratio <= green:
        return "green"
    if ratio <= yellow:
        return "yellow"
    return "red"


def _check(name: str, ok: bool, message: str, details: dict[str, object]) -> HotPathCheck:
    return HotPathCheck(name=name, status="pass" if ok else "fail", message=message, details=details)
