"""Validation gates for the implement_v2 native transcript runtime."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import fnmatch
import json
from pathlib import Path
from typing import Mapping

from ..work_lanes import IMPLEMENT_V2_LANE
from .finish_verifier_planner_policy import finish_verifier_planner_policy
from .native_transcript import IMPLEMENT_V2_NATIVE_RUNTIME_ID, NativeTranscript, NativeTranscriptItem
from .native_transcript import native_proof_manifest_from_transcript, native_transcript_hash
from .native_transcript import validate_native_transcript_pairing
from .registry import get_implement_lane_runtime_view
from .tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID, build_tool_surface_snapshot


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


@dataclass(frozen=True)
class StaticGateAllowlistEntry:
    """Explicit temporary allowance for known M6.25 cleanup debt."""

    path_pattern: str
    symbols: tuple[str, ...]
    owner: str
    action: str
    removal_gate: str
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "path_pattern": self.path_pattern,
            "symbols": list(self.symbols),
            "owner": self.owner,
            "action": self.action,
            "removal_gate": self.removal_gate,
            "reason": self.reason,
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
    default_surface = build_tool_surface_snapshot(lane_config={})
    legacy_surface = build_tool_surface_snapshot(lane_config={"tool_surface_profile_id": MEW_LEGACY_PROFILE_ID})
    planner_policy = finish_verifier_planner_policy({})
    details["default_tool_surface"] = default_surface.request_metadata()
    details["legacy_tool_surface_opt_out"] = legacy_surface.request_metadata()
    details["finish_verifier_planner_policy"] = {
        "enabled": planner_policy.enabled,
        "selection_source": planner_policy.selection_source,
    }
    checks["default_tool_surface_profile_codex_hot_path"] = default_surface.profile_id == CODEX_HOT_PATH_PROFILE_ID
    checks["default_tool_surface_profile_default"] = default_surface.profile_default is True
    checks["planner_policy_default_enabled"] = (
        planner_policy.enabled is True and planner_policy.selection_source == "default_enabled"
    )
    checks["legacy_tool_surface_explicit_opt_out"] = (
        legacy_surface.profile_id == MEW_LEGACY_PROFILE_ID
        and legacy_surface.profile_default is False
        and legacy_surface.profile_selection_source == "legacy_opt_out"
    )

    command_scan = _scan_command_route(source_path)
    details["command_route"] = command_scan
    checks["command_route_no_live_json_call"] = command_scan.get("run_live_json_implement_v2") is False
    checks["command_route_no_model_json_runtime_literal"] = command_scan.get("model_json_runtime_literal") is False
    checks["command_route_has_native_runner"] = command_scan.get("run_live_native_implement_v2") is True
    package_scan = _scan_package_surface(source_path)
    details["package_surface"] = package_scan
    checks["package_surface_exists"] = package_scan.get("exists") is True
    for symbol, present in _package_surface_banned_symbols(package_scan).items():
        checks[f"package_surface_no_{symbol}"] = present is False
    production_scan = _scan_native_production_paths(source_path)
    details["native_production_paths"] = production_scan
    details["native_production_static_allowlist"] = [
        entry.as_dict() for entry in _native_production_legacy_allowlist()
    ]
    checks["native_production_paths_exist"] = all(
        bool(item.get("exists")) for item in production_scan
    )
    checks["native_production_static_allowlist_explicit"] = bool(_native_production_legacy_allowlist())
    checks["native_production_paths_no_legacy_symbols"] = not any(
        item.get("legacy_hits") for item in production_scan
    )
    planner_policy_scan = _scan_planner_policy_boundary_paths(source_path)
    details["planner_policy_boundary_paths"] = planner_policy_scan
    checks["native_production_paths_no_direct_planner_config_reads"] = not any(
        item.get("planner_config_hits") for item in planner_policy_scan
    )
    research_lane_boundary_scan = _scan_research_lane_import_boundary(source_path)
    details["research_lane_import_boundary"] = research_lane_boundary_scan
    checks["research_lane_no_implement_runtime_imports"] = not any(
        item.get("forbidden_import_hits") for item in research_lane_boundary_scan
    )

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
        "run_live_native_implement_v2": "run_live_native_implement_v2" in text,
        "run_unavailable_native_implement_v2": "run_unavailable_native_implement_v2" in text,
    }


def _scan_package_surface(source_root: Path) -> dict[str, object]:
    path = source_root / "src" / "mew" / "implement_lane" / "__init__.py"
    symbols = _legacy_public_surface_symbols()
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            **{symbol: None for symbol in symbols},
        }
    text = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "exists": True,
        **{symbol: symbol in text for symbol in symbols},
    }


def _legacy_public_surface_symbols() -> tuple[str, ...]:
    return (
        "run_live_json_implement_v2",
        "run_fake_exec_implement_v2",
        "run_fake_read_only_implement_v2",
        "run_fake_write_implement_v2",
        "run_unavailable_implement_v2",
        "JsonModelProviderAdapter",
        "FakeProviderAdapter",
        "FakeProviderToolCall",
        "LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID",
        "list_v2_base_tool_specs",
        "list_v2_tool_specs_for_mode",
        "list_v2_tool_specs_for_task",
    )


def _package_surface_banned_symbols(package_scan: Mapping[str, object]) -> dict[str, object]:
    return {symbol: package_scan.get(symbol) for symbol in _legacy_public_surface_symbols()}


def _native_production_relative_paths(source_root: Path) -> tuple[str, ...]:
    return _production_scan_relative_paths(source_root)


def _production_scan_relative_paths(source_root: Path) -> tuple[str, ...]:
    candidates = [source_root / "src" / "mew" / "commands.py"]
    for package in ("implement_lane", "lane_substrate", "research_lane"):
        package_root = source_root / "src" / "mew" / package
        if package_root.exists():
            candidates.extend(sorted(package_root.rglob("*.py")))
    relative_paths = []
    for path in candidates:
        try:
            relative_paths.append(path.relative_to(source_root).as_posix())
        except ValueError:
            relative_paths.append(path.as_posix())
    return tuple(dict.fromkeys(relative_paths))


def _native_production_banned_symbols() -> tuple[str, ...]:
    # This gate freezes the M6.25 production boundary. Known pre-cleanup debt is
    # allowed only through _native_production_legacy_allowlist().
    return (
        "run_live_json_implement_v2",
        "JsonModelProviderAdapter",
        "model_json_tool_loop",
        "implement_v2_model_json_tool_loop",
        "from .v2_runtime import",
        "from mew.implement_lane.v2_runtime import",
        "legacy_model_json_runtime",
        "legacy_model_json_provider",
        "list_v2_base_tool_specs",
        "list_v2_tool_specs_for_mode",
        "list_v2_tool_specs_for_task",
        "workframe_variants",
        "from .workframe_variants import",
        "from mew.implement_lane.workframe_variants import",
        "project_workframe_with_variant",
        "reduce_workframe_with_variant",
        "DEFAULT_WORKFRAME_VARIANT",
        "CommonWorkFrameInputs",
        "list_workframe_variants",
        "workframe_variant_transition_contract",
        "workframe_variant_transcript_first",
        "workframe_variant_transcript_tool_nav",
        "task_contract_compiler",
        "task_contract_compiler_mode",
        "task_contract_compiler_model",
        "task_contract_compiler_timeout_seconds",
        "task_contract_compiler_required",
        "legacy_task_contract",
        "task_contract_legacy",
        "compiled_task_contract",
        "finish_acceptance_gate_decision",
        "_finish_acceptance_action",
        "_acceptance_session_from_tool_results",
        "_typed_acceptance_session_from_tool_results",
        'provider = "model_json"',
        "_live_json_prompt",
        "_normalize_live_json_payload",
        "call_model_json_with_retries",
        "LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID",
        "history_json:",
        "frontier_state_update",
    )


def _native_production_legacy_allowlist() -> tuple[StaticGateAllowlistEntry, ...]:
    all_symbols = _native_production_banned_symbols()
    legacy_projection_field_symbols = (
        "history_json:",
        "frontier_state_update",
    )
    return (
        StaticGateAllowlistEntry(
            "src/mew/implement_lane/affordance_visibility.py",
            ("frontier_state_update",),
            owner="Phase 4 provider-visible field cleanup",
            action="rename-or-semantic-exempt",
            removal_gate="field guard avoids legacy projection token or gate uses semantic leak detection",
            reason="current guard names the forbidden legacy field explicitly",
        ),
        StaticGateAllowlistEntry(
            "src/mew/implement_lane/hot_path_fastcheck.py",
            legacy_projection_field_symbols,
            owner="Phase 4 diagnostic split",
            action="split",
            removal_gate="native fastcheck no longer scans legacy projection fields by raw token",
        ),
        StaticGateAllowlistEntry(
            "src/mew/implement_lane/native_validation.py",
            all_symbols,
            owner="Phase 0 static gate",
            action="keep-gate-definitions",
            removal_gate="banned symbol list no longer needs to mention retired legacy names",
        ),
        StaticGateAllowlistEntry(
            "src/mew/implement_lane/native_transcript.py",
            ("LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID", "model_json_tool_loop", "implement_v2_model_json_tool_loop"),
            owner="Phase 2 forbidden-evidence compatibility marker",
            action="keep-rejected-evidence-marker",
            removal_gate="native artifact contract no longer needs legacy forbidden runtime-id compatibility field",
            reason="metadata-only marker used to reject legacy model-json artifacts; not a route or package export",
        ),
        StaticGateAllowlistEntry(
            "src/mew/implement_lane/tool_profiles/mew_legacy.py",
            (
                "list_v2_base_tool_specs",
                "list_v2_tool_specs_for_mode",
                "list_v2_tool_specs_for_task",
            ),
            owner="Phase 2 tool profile quarantine",
            action="isolate-or-delete",
            removal_gate="legacy tool surface cannot be selected by production runtime",
        ),
        StaticGateAllowlistEntry(
            "src/mew/implement_lane/tool_surface_ab_report.py",
            ("frontier_state_update",),
            owner="Phase 4 provider-visible field cleanup",
            action="rename-or-semantic-exempt",
            removal_gate="A/B report avoids legacy projection token or gate uses semantic leak detection",
            reason="current report names the forbidden legacy field explicitly",
        ),
    )


def _allowed_banned_symbols_for_path(relative_path: str) -> tuple[str, ...]:
    symbols: list[str] = []
    for entry in _native_production_legacy_allowlist():
        if fnmatch.fnmatch(relative_path, entry.path_pattern):
            symbols.extend(entry.symbols)
    return tuple(dict.fromkeys(symbols))


def _scan_native_production_paths(source_root: Path) -> tuple[dict[str, object], ...]:
    scanned: list[dict[str, object]] = []
    for relative_path in _native_production_relative_paths(source_root):
        path = source_root / relative_path
        if not path.exists():
            scanned.append({"path": relative_path, "exists": False, "legacy_hits": {}, "allowed_legacy_hits": {}})
            continue
        text = path.read_text(encoding="utf-8")
        all_hits = {
            symbol: text.count(symbol)
            for symbol in _native_production_banned_symbols()
            if symbol in text
        }
        allowed_symbols = set(_allowed_banned_symbols_for_path(relative_path))
        allowed_hits = {symbol: count for symbol, count in all_hits.items() if symbol in allowed_symbols}
        unallowed_hits = {symbol: count for symbol, count in all_hits.items() if symbol not in allowed_symbols}
        scanned.append(
            {
                "path": relative_path,
                "exists": True,
                "legacy_hits": unallowed_hits,
                "allowed_legacy_hits": allowed_hits,
            }
        )
    return tuple(scanned)


def _planner_policy_boundary_relative_paths(source_root: Path) -> tuple[str, ...]:
    return _production_scan_relative_paths(source_root)


def _planner_config_direct_read_keys() -> tuple[str, ...]:
    return (
        "finish_verifier_planner_enabled",
        "finish_verifier_planner",
        "experimental_finish_verifier_planner",
    )


class _PlannerConfigReadVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: dict[str, int] = {}

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "lane_config"
            and node.args
        ):
            key = _planner_config_key(node.args[0])
            if key:
                self._record(f'lane_config.get("{key}")')
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name) and node.value.id == "lane_config":
            key = _planner_config_key(node.slice)
            if key:
                self._record(f'lane_config["{key}"]')
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if (
            len(node.ops) == 1
            and isinstance(node.ops[0], (ast.In, ast.NotIn))
            and len(node.comparators) == 1
            and isinstance(node.comparators[0], ast.Name)
            and node.comparators[0].id == "lane_config"
        ):
            key = _planner_config_key(node.left)
            if key:
                self._record(f'"{key}" in lane_config')
        self.generic_visit(node)

    def _record(self, label: str) -> None:
        self.hits[label] = self.hits.get(label, 0) + 1


def _planner_config_key(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value
        if value in _planner_config_direct_read_keys():
            return value
    return ""


def _planner_config_direct_read_hits(text: str) -> dict[str, int]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    visitor = _PlannerConfigReadVisitor()
    visitor.visit(tree)
    return dict(visitor.hits)


def _scan_planner_policy_boundary_paths(source_root: Path) -> tuple[dict[str, object], ...]:
    scanned: list[dict[str, object]] = []
    for relative_path in _planner_policy_boundary_relative_paths(source_root):
        path = source_root / relative_path
        if not path.exists():
            scanned.append({"path": relative_path, "exists": False, "planner_config_hits": {}})
            continue
        text = path.read_text(encoding="utf-8")
        hits = _planner_config_direct_read_hits(text)
        scanned.append({"path": relative_path, "exists": True, "planner_config_hits": hits})
    return tuple(scanned)


def _research_lane_forbidden_import_roots() -> tuple[str, ...]:
    return (
        "mew.implement_lane",
    )


def _imported_module_names(text: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ()
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                names.append(module)
            module_already_matches = any(
                module == root or module.startswith(f"{root}.")
                for root in _research_lane_forbidden_import_roots()
            )
            if not module_already_matches:
                names.extend(f"{module}.{alias.name}" if module else alias.name for alias in node.names)
    return tuple(names)


def _forbidden_research_lane_import_hits(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for name in _imported_module_names(text):
        for root in _research_lane_forbidden_import_roots():
            if name == root or name.startswith(f"{root}."):
                hits[root] = hits.get(root, 0) + 1
    return hits


def _scan_research_lane_import_boundary(source_root: Path) -> tuple[dict[str, object], ...]:
    package_root = source_root / "src" / "mew" / "research_lane"
    if not package_root.exists():
        return ()
    scanned: list[dict[str, object]] = []
    for path in sorted(package_root.rglob("*.py")):
        try:
            relative_path = path.relative_to(source_root).as_posix()
        except ValueError:
            relative_path = path.as_posix()
        text = path.read_text(encoding="utf-8")
        scanned.append(
            {
                "path": relative_path,
                "exists": True,
                "forbidden_import_hits": _forbidden_research_lane_import_hits(text),
            }
        )
    return tuple(scanned)


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
