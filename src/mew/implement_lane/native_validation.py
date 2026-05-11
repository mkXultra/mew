"""Validation gates for the implement_v2 native transcript runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Mapping

from ..work_lanes import IMPLEMENT_V2_LANE
from .native_transcript import IMPLEMENT_V2_NATIVE_RUNTIME_ID, NativeTranscript, NativeTranscriptItem
from .native_transcript import native_proof_manifest_from_transcript, native_transcript_hash
from .native_transcript import validate_native_transcript_pairing
from .registry import get_implement_lane_runtime_view


NATIVE_VALIDATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class NativeLoopGateResult:
    """Result of the Phase 6 native-loop validation gate."""

    ok: bool
    checks: dict[str, bool]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    details: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": NATIVE_VALIDATION_SCHEMA_VERSION,
            "ok": self.ok,
            "checks": dict(self.checks),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": dict(self.details),
        }


def validate_native_loop_gate(
    *,
    source_root: str | Path = ".",
    artifact: str | Path | None = None,
) -> NativeLoopGateResult:
    """Validate that selected implement_v2 evidence is native-loop evidence.

    This gate is intentionally deterministic and cheap. It runs before live
    step-shape or speed proof, so a stale model-JSON artifact cannot be counted
    as native progress after context compression.
    """

    source_path = Path(source_root).expanduser().resolve(strict=False)
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}
    details: dict[str, object] = {"source_root": str(source_path)}

    runtime = get_implement_lane_runtime_view(IMPLEMENT_V2_LANE)
    checks["registry_native_runtime_id"] = runtime.runtime_id == IMPLEMENT_V2_NATIVE_RUNTIME_ID
    checks["registry_provider_native_loop"] = runtime.provider_native_tool_loop is True

    command_scan = _scan_command_route(source_path)
    details["command_route"] = command_scan
    checks["command_route_no_live_json_call"] = command_scan.get("run_live_json_implement_v2") is False
    checks["command_route_no_model_json_runtime_literal"] = command_scan.get("model_json_runtime_literal") is False
    checks["command_route_has_native_runner"] = command_scan.get("run_unavailable_native_implement_v2") is True

    fixture_manifest = native_proof_manifest_from_transcript(_validation_fixture_transcript())
    fixture_pairing = fixture_manifest.get("pairing") if isinstance(fixture_manifest.get("pairing"), dict) else {}
    details["fixture_manifest"] = {
        "runtime_id": fixture_manifest.get("runtime_id"),
        "transport_kind": fixture_manifest.get("transport_kind"),
        "pairing": fixture_pairing,
    }
    checks["fixture_pairing_valid"] = fixture_pairing.get("valid") is True
    checks["fixture_manifest_native_runtime_id"] = fixture_manifest.get("runtime_id") == IMPLEMENT_V2_NATIVE_RUNTIME_ID
    checks["fixture_manifest_not_model_json"] = _manifest_is_native(fixture_manifest)

    if artifact is not None:
        manifest_path = _resolve_manifest_path(Path(artifact).expanduser())
        details["artifact_manifest_path"] = str(manifest_path)
        try:
            manifest = _read_json_object(manifest_path)
        except Exception as exc:  # pragma: no cover - defensive error reporting
            manifest = {}
            errors.append(f"artifact_manifest_read_failed:{exc}")
        try:
            transcript = _read_authoritative_native_transcript(manifest_path.parent)
        except Exception as exc:
            transcript = None
            errors.append(f"artifact_transcript_read_failed:{exc}")
        artifact_checks = _validate_manifest(manifest, transcript=transcript)
        details["artifact_manifest"] = {
            "runtime_id": manifest.get("runtime_id"),
            "transport_kind": manifest.get("transport_kind"),
            "metrics": manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {},
        }
        checks.update({f"artifact_{key}": value for key, value in artifact_checks.items()})
    else:
        warnings.append("artifact_not_provided; validated static route and native fixture only")

    for key, passed in checks.items():
        if not passed:
            errors.append(key)
    return NativeLoopGateResult(
        ok=not errors,
        checks=checks,
        errors=tuple(errors),
        warnings=tuple(warnings),
        details=details,
    )


def _scan_command_route(source_root: Path) -> dict[str, object]:
    path = source_root / "src" / "mew" / "commands.py"
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "run_live_json_implement_v2": "run_live_json_implement_v2" in text,
        "model_json_runtime_literal": "implement_v2_model_json_tool_loop" in text,
        "native_runtime_literal": IMPLEMENT_V2_NATIVE_RUNTIME_ID in text,
        "run_unavailable_native_implement_v2": "run_unavailable_native_implement_v2" in text,
    }


def _validation_fixture_transcript() -> NativeTranscript:
    lane_attempt_id = "phase6-native-validation:task:implement_v2:native"
    call = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id=lane_attempt_id,
        provider="validation",
        model="fixture",
        response_id="response-1",
        provider_item_id="item-call-1",
        output_index=0,
        kind="function_call",
        call_id="call-1",
        tool_name="read_file",
        arguments_json_text='{"path":"README.md"}',
    )
    output = NativeTranscriptItem(
        sequence=2,
        turn_id="turn-1",
        lane_attempt_id=lane_attempt_id,
        provider="validation",
        model="fixture",
        response_id="response-1",
        provider_item_id="item-output-1",
        output_index=0,
        kind="function_call_output",
        call_id="call-1",
        tool_name="read_file",
        output_text_or_ref="read_file result: completed; content_refs=validation://readme",
        status="completed",
        content_refs=("validation://readme",),
    )
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="validation",
        model="fixture",
        items=(call, output),
    )
    validation = validate_native_transcript_pairing(transcript)
    if not validation.valid:
        raise AssertionError(f"invalid built-in validation fixture: {validation.errors}")
    return transcript


def _resolve_manifest_path(path: Path) -> Path:
    if path.is_file():
        return path.resolve(strict=False)
    candidates = (
        path / "proof-manifest.json",
        path / "implement_v2" / "proof-manifest.json",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve(strict=False)
    recursive = sorted(path.rglob("implement_v2/proof-manifest.json")) if path.exists() and path.is_dir() else []
    if recursive:
        return recursive[0].resolve(strict=False)
    raise FileNotFoundError(f"no implement_v2 proof-manifest.json under: {path}")


def _read_json_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return dict(payload)


def _read_authoritative_native_transcript(root: Path) -> NativeTranscript:
    transcript_path = root / "response_transcript.json"
    items_path = root / "response_items.jsonl"
    if not transcript_path.exists():
        raise FileNotFoundError(f"missing authoritative transcript: {transcript_path}")
    if not items_path.exists():
        raise FileNotFoundError(f"missing authoritative response items: {items_path}")
    payload = _read_json_object(transcript_path)
    transcript = NativeTranscript(
        lane_attempt_id=str(payload.get("lane_attempt_id") or ""),
        provider=str(payload.get("provider") or ""),
        model=str(payload.get("model") or ""),
        items=tuple(_native_item_from_mapping(item) for item in payload.get("items") or [] if isinstance(item, Mapping)),
    )
    response_items = [
        json.loads(line)
        for line in items_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    transcript_items = [item.as_dict() for item in transcript.items]
    if response_items != transcript_items:
        raise ValueError("response_items.jsonl does not match response_transcript.json items")
    return transcript


def _native_item_from_mapping(item: Mapping[str, object]) -> NativeTranscriptItem:
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
        content_refs=tuple(str(ref) for ref in item.get("content_refs") or []),
        evidence_refs=tuple(str(ref) for ref in item.get("evidence_refs") or []),
        sidecar_refs=tuple(str(ref) for ref in item.get("sidecar_refs") or []),
    )


def _validate_manifest(manifest: Mapping[str, object], *, transcript: NativeTranscript | None) -> dict[str, bool]:
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    pairing = manifest.get("pairing") if isinstance(manifest.get("pairing"), dict) else {}
    recomputed_manifest = native_proof_manifest_from_transcript(transcript) if transcript is not None else {}
    recomputed_pairing = (
        recomputed_manifest.get("pairing") if isinstance(recomputed_manifest.get("pairing"), dict) else {}
    )
    return {
        "native_runtime_id": manifest.get("runtime_id") == IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "native_transport": _manifest_is_native(manifest),
        "pairing_valid": pairing.get("valid") is True
        or metrics.get("pairing_valid") is True,
        "authoritative_transcript_present": transcript is not None,
        "authoritative_pairing_valid": recomputed_pairing.get("valid") is True,
        "transcript_hash_matches": bool(transcript)
        and str(manifest.get("transcript_hash") or "") == native_transcript_hash(transcript),
        "manifest_recomputes": bool(recomputed_manifest)
        and recomputed_manifest.get("runtime_id") == manifest.get("runtime_id")
        and recomputed_manifest.get("transcript_hash") == manifest.get("transcript_hash"),
        "provider_native_tool_loop": metrics.get("provider_native_tool_loop") is True,
        "model_json_main_path_not_detected": metrics.get("model_json_main_path_detected") is not True,
    }


def _manifest_is_native(manifest: Mapping[str, object]) -> bool:
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    transport_kind = str(manifest.get("transport_kind") or metrics.get("transport_kind") or "")
    if transport_kind in {"legacy_model_json", "model_json"}:
        return False
    return manifest.get("runtime_id") == IMPLEMENT_V2_NATIVE_RUNTIME_ID


__all__ = ["NATIVE_VALIDATION_SCHEMA_VERSION", "NativeLoopGateResult", "validate_native_loop_gate"]
