"""Deterministic implement_v2 tool-loop diagnostics.

The tool lab intentionally avoids model calls. It lets operators replay saved
proof manifests or execute one bounded tool call and inspect the substrate
state that usually only appears after a costly Harbor run.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import replace
from pathlib import Path

from ..work_lanes import IMPLEMENT_V2_LANE
from .exec_runtime import ImplementV2ManagedExecRuntime
from .types import ToolCallEnvelope, ToolResultEnvelope

TOOL_LAB_SCHEMA_VERSION = 1
_ABSOLUTE_PATH_LITERAL_RE = re.compile(r"(?<![:\w./-])/(?:[^\s'\";|&<>`$(){},]+)")
_RELATIVE_TRAVERSAL_LITERAL_RE = re.compile(r"(?<![\w./-])(?:\.\./)+(?:[^\s'\";|&<>`$(){},]+)")
_WRITE_REDIRECT_TOKEN_RE = re.compile(r"^(?:\d?>>?|&>>?|>\|?)$")
_INLINE_WRITE_REDIRECT_RE = re.compile(r"^(?:\d?>>?|&>>?|>\|?)(.+)$")


def analyze_implement_v2_tool_lab_artifact(
    path: object,
    *,
    workspace: object = "",
    source_mutation_roots: tuple[str, ...] | list[str] = (),
    target_paths: tuple[str, ...] | list[str] = (),
    probe_threshold: int | None = None,
    requires_deep_runtime_coverage: bool = False,
) -> dict[str, object]:
    """Analyze a saved implement_v2 proof manifest or artifact directory."""

    manifest_path = resolve_implement_v2_manifest_path(path)
    manifest = _load_json_file(manifest_path)
    return analyze_implement_v2_tool_lab_manifest(
        manifest,
        manifest_path=str(manifest_path),
        workspace=workspace,
        source_mutation_roots=tuple(source_mutation_roots),
        target_paths=tuple(target_paths),
        probe_threshold=probe_threshold,
        requires_deep_runtime_coverage=requires_deep_runtime_coverage,
    )


def run_implement_v2_tool_lab_command(
    *,
    command: str,
    workspace: object = ".",
    cwd: object = ".",
    allowed_read_roots: tuple[str, ...] | list[str] = (),
    allowed_write_roots: tuple[str, ...] | list[str] = (),
    source_mutation_roots: tuple[str, ...] | list[str] = (),
    target_paths: tuple[str, ...] | list[str] = (),
    timeout: float | None = None,
    command_intent: str = "probe",
    probe_threshold: int | None = None,
    requires_deep_runtime_coverage: bool = False,
) -> dict[str, object]:
    """Execute one deterministic run_command through implement_v2 exec mode."""

    workspace_path = Path(str(workspace or ".")).expanduser().resolve(strict=False)
    read_roots = tuple(str(root) for root in (allowed_read_roots or [str(workspace_path)]))
    write_roots = tuple(str(root) for root in (allowed_write_roots or [str(workspace_path)]))
    source_roots = _effective_source_mutation_roots(
        workspace=workspace_path,
        source_mutation_roots=tuple(source_mutation_roots),
    )
    scope_error = _tool_lab_command_scope_error(
        command,
        workspace_path=workspace_path,
        write_roots=write_roots,
    )
    if scope_error:
        raise ValueError(scope_error)
    arguments: dict[str, object] = {
        "command": str(command),
        "cwd": str(cwd or "."),
        "command_intent": str(command_intent or "probe"),
    }
    if timeout is not None:
        arguments["timeout"] = float(timeout)
    call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:tool-lab",
        provider="native_tool_lab",
        provider_message_id="tool-lab-message",
        provider_call_id="tool-lab-command",
        mew_tool_call_id="mew-tool-lab-command",
        turn_index=1,
        sequence_index=1,
        tool_name="run_command",
        arguments=arguments,
    )
    runtime = ImplementV2ManagedExecRuntime(
        workspace=workspace_path,
        allowed_roots=read_roots,
        allow_shell=True,
        run_command_available=True,
        task_contract={"goal": "implement_v2 native tool-lab deterministic command diagnostic"},
        source_mutation_roots=source_roots,
        allowed_write_roots=write_roots,
        auto_approve_writes=True,
    )
    tool_result = runtime.execute(call)
    manifest = _native_tool_lab_manifest(call, tool_result)
    analysis = analyze_implement_v2_tool_lab_manifest(
        manifest,
        manifest_path="",
        workspace=workspace,
        source_mutation_roots=source_roots,
        target_paths=tuple(target_paths),
        probe_threshold=probe_threshold,
        requires_deep_runtime_coverage=requires_deep_runtime_coverage,
    )
    analysis["mode"] = "command"
    analysis["command"] = {
        "text": str(command),
        "cwd": str(cwd or "."),
        "intent": str(command_intent or "probe"),
        "timeout": timeout,
    }
    analysis["result_status"] = tool_result.status
    analysis["result_metrics"] = dict(manifest.get("metrics") or {})
    return analysis


def analyze_implement_v2_tool_lab_manifest(
    manifest: dict[str, object],
    *,
    manifest_path: str = "",
    workspace: object = "",
    source_mutation_roots: tuple[str, ...] | list[str] = (),
    target_paths: tuple[str, ...] | list[str] = (),
    probe_threshold: int | None = None,
    requires_deep_runtime_coverage: bool = False,
) -> dict[str, object]:
    tool_calls = tuple(_tool_call_from_dict(item) for item in _list_of_dicts(manifest.get("tool_calls")))
    tool_results = tuple(_tool_result_from_dict(item) for item in _list_of_dicts(manifest.get("tool_results")))
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    source_roots = _effective_source_mutation_roots(
        workspace=workspace,
        source_mutation_roots=tuple(source_mutation_roots),
    )
    mutations = _collect_source_tree_mutations(tool_results)
    suspicious = _suspicious_source_tree_mutations(
        mutations,
        workspace=workspace,
        source_mutation_roots=source_roots,
    )
    observed_readiness = dict(metrics.get("first_write_readiness") or {}) if isinstance(metrics, dict) else {}
    recomputed_readiness: dict[str, object] = {}
    if target_paths:
        active_work_todo = {
            "id": "tool-lab",
            "status": "drafting",
            "source": {"target_paths": list(target_paths)},
        }
        trusted_tool_results = _tool_results_with_trusted_source_mutations(
            tool_results,
            workspace=workspace,
            source_mutation_roots=source_roots,
            target_paths=tuple(target_paths),
        )
        recomputed_readiness = _first_write_readiness_from_trace(
            active_work_todo,
            tool_calls=tool_calls,
            tool_results=trusted_tool_results,
            probe_threshold=int(probe_threshold or observed_readiness.get("probe_threshold") or 3),
            requires_deep_runtime_coverage=requires_deep_runtime_coverage,
            source_mutation_roots=source_roots,
        )
    hot_path = metrics.get("hot_path_projection") if isinstance(metrics, dict) else {}
    provider_visible_bytes = hot_path.get("provider_visible_tool_result_bytes") if isinstance(hot_path, dict) else None
    provider_visible_source = "manifest_metric" if provider_visible_bytes is not None else "computed_tool_results"
    if provider_visible_bytes is None:
        provider_visible_bytes = _provider_visible_tool_result_bytes(tool_results)
    return {
        "schema_version": TOOL_LAB_SCHEMA_VERSION,
        "mode": "artifact",
        "manifest_path": manifest_path,
        "lane": str(manifest.get("lane") or ""),
        "lane_attempt_id": str(manifest.get("lane_attempt_id") or ""),
        "tool_call_count": len(tool_calls),
        "tool_result_count": len(tool_results),
        "source_tree_mutation_count": len(mutations),
        "source_tree_mutations": mutations,
        "suspicious_source_tree_mutation_count": len(suspicious),
        "suspicious_source_tree_mutations": suspicious,
        "first_write_readiness": {
            "observed": observed_readiness,
            "recomputed": recomputed_readiness,
        },
        "provider_visible_tool_result_bytes": provider_visible_bytes,
        "provider_visible_tool_result_bytes_source": provider_visible_source,
        "replay_valid": metrics.get("replay_valid") if isinstance(metrics, dict) else None,
    }


def resolve_implement_v2_manifest_path(path: object) -> Path:
    raw = Path(str(path or "")).expanduser()
    if raw.is_file():
        return raw.resolve(strict=False)
    if not raw.exists():
        raise FileNotFoundError(f"implement_v2 artifact path does not exist: {raw}")
    candidates = (
        raw / "implement_v2" / "proof-manifest.json",
        raw / "proof-manifest.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve(strict=False)
    recursive = sorted(raw.rglob("implement_v2/proof-manifest.json"))
    if recursive:
        return recursive[0].resolve(strict=False)
    raise FileNotFoundError(f"no implement_v2 proof-manifest.json under: {raw}")


def format_implement_v2_tool_lab_text(result: dict[str, object]) -> str:
    lines = [
        "implement_v2 tool-lab",
        f"mode: {result.get('mode')}",
        f"manifest: {result.get('manifest_path') or '(generated)'}",
        f"tool calls/results: {result.get('tool_call_count')}/{result.get('tool_result_count')}",
        f"source mutations: {result.get('source_tree_mutation_count')}",
        f"suspicious source mutations: {result.get('suspicious_source_tree_mutation_count')}",
    ]
    readiness = result.get("first_write_readiness") if isinstance(result.get("first_write_readiness"), dict) else {}
    observed = readiness.get("observed") if isinstance(readiness, dict) else {}
    recomputed = readiness.get("recomputed") if isinstance(readiness, dict) else {}
    if isinstance(observed, dict) and observed:
        lines.append(f"observed first-write: {observed.get('status')} due={observed.get('first_write_due')}")
    if isinstance(recomputed, dict) and recomputed:
        lines.append(f"recomputed first-write: {recomputed.get('status')} due={recomputed.get('first_write_due')}")
    suspicious = result.get("suspicious_source_tree_mutations")
    if isinstance(suspicious, list) and suspicious:
        lines.append("suspicious paths:")
        for item in suspicious[:10]:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('path')} ({item.get('reason')}) from {item.get('provider_call_id')}")
    return "\n".join(lines)


def _load_json_file(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _list_of_dicts(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def _tool_call_from_dict(data: dict[str, object]) -> ToolCallEnvelope:
    return ToolCallEnvelope(
        lane_attempt_id=str(data.get("lane_attempt_id") or ""),
        provider=str(data.get("provider") or ""),
        provider_message_id=str(data.get("provider_message_id") or ""),
        provider_call_id=str(data.get("provider_call_id") or ""),
        mew_tool_call_id=str(data.get("mew_tool_call_id") or ""),
        turn_index=int(data.get("turn_index") or 0),
        sequence_index=int(data.get("sequence_index") or 0),
        tool_name=str(data.get("tool_name") or ""),
        arguments=dict(data.get("arguments") or {}) if isinstance(data.get("arguments"), dict) else {},
        raw_arguments_ref=str(data.get("raw_arguments_ref") or ""),
        received_at=str(data.get("received_at") or ""),
        status=data.get("status") or "received",  # type: ignore[arg-type]
    )


def _tool_result_from_dict(data: dict[str, object]) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id=str(data.get("lane_attempt_id") or ""),
        provider_call_id=str(data.get("provider_call_id") or ""),
        mew_tool_call_id=str(data.get("mew_tool_call_id") or ""),
        tool_name=str(data.get("tool_name") or ""),
        status=data.get("status") or "failed",  # type: ignore[arg-type]
        is_error=bool(data.get("is_error")),
        content=tuple(data.get("content") or ()) if isinstance(data.get("content"), list) else (),
        content_refs=tuple(str(item) for item in (data.get("content_refs") or ()) if isinstance(item, str))
        if isinstance(data.get("content_refs"), list)
        else (),
        evidence_refs=tuple(str(item) for item in (data.get("evidence_refs") or ()) if isinstance(item, str))
        if isinstance(data.get("evidence_refs"), list)
        else (),
        side_effects=tuple(dict(item) for item in (data.get("side_effects") or ()) if isinstance(item, dict))
        if isinstance(data.get("side_effects"), list)
        else (),
        started_at=str(data.get("started_at") or ""),
        finished_at=str(data.get("finished_at") or ""),
    )


def _collect_source_tree_mutations(results: tuple[ToolResultEnvelope, ...]) -> list[dict[str, object]]:
    mutations: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for result in results:
        records: list[dict[str, object]] = []
        for effect in result.side_effects:
            if effect.get("kind") in {"source_tree_mutation", "process_source_observation"} and isinstance(
                effect.get("record"), dict
            ):
                records.append({**dict(effect["record"]), "observation_kind": str(effect.get("kind") or "")})
        if not records:
            for content in result.content:
                if not isinstance(content, dict):
                    continue
                for key, kind in (
                    ("source_tree_mutations", "source_tree_mutation"),
                    ("process_source_observations", "process_source_observation"),
                ):
                    if not isinstance(content.get(key), list):
                        continue
                    records.extend(
                        {**dict(item), "observation_kind": kind} for item in content[key] if isinstance(item, dict)
                    )
        for record in records:
            for change in _list_of_dicts(record.get("changes")):
                path = str(change.get("path") or "")
                key = (str(record.get("provider_call_id") or result.provider_call_id), path, str(change.get("change") or ""))
                if key in seen:
                    continue
                seen.add(key)
                mutations.append(
                    {
                        "provider_call_id": key[0],
                        "command_run_id": str(record.get("command_run_id") or ""),
                        "path": path,
                        "change": str(change.get("change") or ""),
                        "before_size": change.get("before_size"),
                        "after_size": change.get("after_size"),
                        "observation_kind": str(record.get("observation_kind") or ""),
                    }
                )
    return mutations


def _tool_results_with_trusted_source_mutations(
    results: tuple[ToolResultEnvelope, ...],
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
    target_paths: tuple[str, ...],
) -> tuple[ToolResultEnvelope, ...]:
    return tuple(
        replace(
            result,
            content=_content_with_trusted_source_mutations(
                result.content,
                workspace=workspace,
                source_mutation_roots=source_mutation_roots,
                target_paths=target_paths,
            ),
            side_effects=_side_effects_with_trusted_source_mutations(
                result.side_effects,
                workspace=workspace,
                source_mutation_roots=source_mutation_roots,
                target_paths=target_paths,
            ),
        )
        for result in results
    )


def _side_effects_with_trusted_source_mutations(
    effects: tuple[dict[str, object], ...],
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
    target_paths: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    trusted: list[dict[str, object]] = []
    for effect in effects:
        if effect.get("kind") not in {"source_tree_mutation", "process_source_observation"} or not isinstance(
            effect.get("record"), dict
        ):
            trusted.append(dict(effect))
            continue
        record = _trusted_source_mutation_record(
            dict(effect["record"]),
            workspace=workspace,
            source_mutation_roots=source_mutation_roots,
            target_paths=target_paths,
        )
        if record:
            trusted.append({**effect, "record": record})
    return tuple(trusted)


def _content_with_trusted_source_mutations(
    content_items: tuple[object, ...],
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
    target_paths: tuple[str, ...],
) -> tuple[object, ...]:
    trusted_items: list[object] = []
    for item in content_items:
        if not isinstance(item, dict):
            trusted_items.append(item)
            continue
        copied = dict(item)
        saw_source_mutation_shape = False
        for key in ("source_tree_mutations", "process_source_observations"):
            if not isinstance(copied.get(key), list):
                continue
            saw_source_mutation_shape = True
            trusted_records = []
            for record in copied.get(key) or []:
                if isinstance(record, dict):
                    trusted_record = _trusted_source_mutation_record(
                        record,
                        workspace=workspace,
                        source_mutation_roots=source_mutation_roots,
                        target_paths=target_paths,
                    )
                    if trusted_record:
                        trusted_records.append(trusted_record)
            copied[key] = trusted_records
        if not saw_source_mutation_shape:
            trusted_items.append(item)
            continue
        trusted_items.append(copied)
    return tuple(trusted_items)


def _trusted_source_mutation_record(
    record: dict[str, object],
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
    target_paths: tuple[str, ...],
) -> dict[str, object]:
    changes = [
        change
        for change in _list_of_dicts(record.get("changes"))
        if _trusted_source_mutation_path(
            str(change.get("path") or ""),
            workspace=workspace,
            source_mutation_roots=source_mutation_roots,
            target_paths=target_paths,
        )
    ]
    if not changes:
        return {}
    return {**record, "changed_count": len(changes), "changes": changes}


def _trusted_source_mutation_path(
    path: str,
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
    target_paths: tuple[str, ...],
) -> bool:
    trusted_roots = _trusted_mutation_roots(workspace=workspace, source_mutation_roots=source_mutation_roots)
    workspace_path = trusted_roots[0] if trusted_roots else None
    if _suspicious_mutation_reason(path, trusted_roots=trusted_roots):
        return False
    if not target_paths:
        return True
    candidate = _candidate_path(path, workspace_path=workspace_path)
    return any(_path_matches_target(candidate, target, workspace_path=workspace_path) for target in target_paths)


def _suspicious_source_tree_mutations(
    mutations: list[dict[str, object]],
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
) -> list[dict[str, object]]:
    trusted_roots = _trusted_mutation_roots(workspace=workspace, source_mutation_roots=source_mutation_roots)
    suspicious: list[dict[str, object]] = []
    for mutation in mutations:
        path = str(mutation.get("path") or "")
        reason = _suspicious_mutation_reason(path, trusted_roots=trusted_roots)
        if not reason:
            continue
        suspicious.append({**mutation, "reason": reason})
    return suspicious


def _trusted_mutation_roots(*, workspace: object, source_mutation_roots: tuple[str, ...]) -> tuple[Path, ...]:
    return tuple(Path(root).expanduser().resolve(strict=False) for root in _effective_source_mutation_roots(
        workspace=workspace,
        source_mutation_roots=source_mutation_roots,
    ))


def _effective_source_mutation_roots(
    *,
    workspace: object,
    source_mutation_roots: tuple[str, ...],
) -> tuple[str, ...]:
    workspace_path = (
        Path(str(workspace)).expanduser().resolve(strict=False)
        if str(workspace or "").strip()
        else None
    )
    raw_roots = tuple(str(root) for root in source_mutation_roots if str(root or "").strip())
    if not raw_roots and workspace_path is not None:
        raw_roots = (str(workspace_path),)
    roots: list[str] = []
    for raw in raw_roots:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute() and workspace_path is not None:
            candidate = workspace_path / candidate
        resolved = str(candidate.resolve(strict=False))
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _suspicious_mutation_reason(path: str, *, trusted_roots: tuple[Path, ...]) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return "empty_path"
    workspace_path = trusted_roots[0] if trusted_roots else None
    if trusted_roots:
        try:
            candidate = _candidate_path(normalized, workspace_path=workspace_path)
        except OSError:
            return ""
        if not any(candidate == root or _is_relative_to(candidate, root) for root in trusted_roots):
            return "outside_workspace"
        candidate_text = str(candidate).casefold()
        if "/.mew/" in candidate_text or candidate_text.endswith("/.mew"):
            return "mew_spool_path"
        return ""
    lowered = normalized.casefold()
    if lowered.startswith(("/tmp/", "/private/tmp/", "/var/tmp/", "tmp/")):
        return "scratch_tmp_path"
    if "/.mew/" in lowered or lowered.endswith("/.mew"):
        return "mew_spool_path"
    return ""


def _candidate_path(path: str, *, workspace_path: Path | None) -> Path:
    raw_candidate = Path(str(path or "")).expanduser()
    if not raw_candidate.is_absolute() and workspace_path is not None:
        raw_candidate = workspace_path / raw_candidate
    return raw_candidate.resolve(strict=False)


def _path_matches_target(candidate: Path, target: str, *, workspace_path: Path | None) -> bool:
    target_path = _candidate_path(target, workspace_path=workspace_path)
    return candidate == target_path or _is_relative_to(candidate, target_path)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _provider_visible_tool_result_bytes(results: tuple[ToolResultEnvelope, ...]) -> int:
    total = 0
    for result in results:
        payload = _provider_visible_tool_result_for_history(result)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        total += len(encoded)
    return total


def _native_tool_lab_manifest(call: ToolCallEnvelope, result: ToolResultEnvelope) -> dict[str, object]:
    readiness = _first_write_readiness_from_trace(
        {"id": "tool-lab", "status": "drafting", "source": {"target_paths": []}},
        tool_calls=(call,),
        tool_results=(result,),
        probe_threshold=1,
        source_mutation_roots=(),
    )
    return {
        "schema_version": 1,
        "lane": IMPLEMENT_V2_LANE,
        "lane_attempt_id": call.lane_attempt_id,
        "diagnostic_kind": "native_tool_lab",
        "tool_calls": [call.as_dict()],
        "tool_results": [result.as_dict()],
        "metrics": {
            "transport_kind": "provider_native",
            "provider_native_tool_loop": True,
            "model_json_main_path_detected": False,
            "first_write_readiness": readiness,
        },
    }


def _first_write_readiness_from_trace(
    active_work_todo: dict[str, object],
    *,
    tool_calls: tuple[object, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    probe_threshold: int,
    requires_deep_runtime_coverage: bool = False,
    source_mutation_roots: tuple[str, ...] = (),
) -> dict[str, object]:
    if not active_work_todo:
        return {}
    probes = 0
    probe_call_ids: list[str] = []
    first_attempt_turn = 0
    first_attempt_call_id = ""
    first_attempt_tool = ""
    first_mutation_turn = 0
    first_mutation_call_id = ""
    first_mutation_tool = ""
    write_count = 0
    mutation_provider_ids = {str(item.get("provider_call_id") or "") for item in _collect_source_tree_mutations(tool_results)}
    for call, result in zip(tool_calls, tool_results):
        tool_name = str(getattr(call, "tool_name", "") or result.tool_name or "")
        call_id = str(getattr(call, "provider_call_id", "") or result.provider_call_id or "")
        turn = int(getattr(call, "turn_index", 0) or 0)
        is_source_write_tool = tool_name in {"apply_patch", "edit_file", "write_file"}
        is_write_attempt = is_source_write_tool or call_id in mutation_provider_ids
        if is_write_attempt:
            write_count += 1
            if first_attempt_turn <= 0:
                first_attempt_turn = turn
                first_attempt_call_id = call_id
                first_attempt_tool = tool_name
            if result.status == "completed" and (is_source_write_tool or call_id in mutation_provider_ids):
                first_mutation_turn = turn
                first_mutation_call_id = call_id
                first_mutation_tool = tool_name
                break
            continue
        if result.status in {"completed", "failed", "invalid"} and tool_name in {
            "glob",
            "inspect_dir",
            "read_file",
            "search_text",
            "run_command",
        }:
            probes += 1
            if len(probe_call_ids) < 8:
                probe_call_ids.append(call_id)
    threshold = max(1, int(probe_threshold))
    first_write_due = first_mutation_turn <= 0 and probes >= threshold
    target_paths = _active_work_todo_target_paths(active_work_todo)
    readiness = {
        "schema_version": 1,
        "status": "written" if first_mutation_turn > 0 else ("due" if first_write_due else "not_due"),
        "first_write_due": first_write_due,
        "probe_threshold": threshold,
        "probes_seen_without_write": probes if first_mutation_turn <= 0 else 0,
        "probe_count_before_first_write": probes,
        "probe_count_total": probes,
        "write_attempt_count": write_count,
        "first_write_attempt_turn": first_attempt_turn or None,
        "first_write_attempt_latency_turns": max(0, first_attempt_turn - 1) if first_attempt_turn > 0 else None,
        "first_write_attempt_tool": first_attempt_tool,
        "first_write_attempt_provider_call_id": first_attempt_call_id,
        "first_source_mutation_turn": first_mutation_turn or None,
        "first_write_latency_turns": max(0, first_mutation_turn - 1) if first_mutation_turn > 0 else None,
        "first_write_tool": first_mutation_tool,
        "first_write_provider_call_id": first_mutation_call_id,
        "target_paths": target_paths,
        "probe_provider_call_ids": probe_call_ids,
        "source": "native_tool_lab_trace",
    }
    if requires_deep_runtime_coverage:
        readiness["prewrite_probe_missing_categories"] = ()
    return {key: value for key, value in readiness.items() if value not in ("", [], {}, None)}


def _active_work_todo_target_paths(active_work_todo: dict[str, object]) -> list[str]:
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    return [str(path)[:240] for path in source.get("target_paths") or [] if str(path or "").strip()][:8]


def _provider_visible_tool_result_for_history(result: ToolResultEnvelope) -> dict[str, object]:
    return {
        "provider_call_id": result.provider_call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "content": result.provider_visible_content(),
    }


def _tool_lab_command_scope_error(command: str, *, workspace_path: Path, write_roots: tuple[str, ...]) -> str:
    root_paths = tuple(_candidate_path(root, workspace_path=workspace_path) for root in write_roots if str(root).strip())
    for literal in _path_literals(command):
        literal_path = _candidate_path(literal, workspace_path=workspace_path)
        if any(literal_path == root or _is_relative_to(literal_path, root) for root in root_paths):
            continue
        return (
            "command mode refuses path literals outside tracked write roots: "
            f"{literal} (use --allow-write for the real output root or keep fixtures under --workspace)"
        )
    for target in _shell_write_redirect_targets(command):
        if target.startswith("&"):
            continue
        target_path = _candidate_path(target, workspace_path=workspace_path)
        if any(target_path == root or _is_relative_to(target_path, root) for root in root_paths):
            continue
        return (
            "command mode refuses write redirection outside tracked write roots: "
            f"{target} (use --allow-write for the real output root or write under --workspace)"
        )
    return ""


def _path_literals(command: str) -> tuple[str, ...]:
    literals: list[str] = []
    for match in _ABSOLUTE_PATH_LITERAL_RE.finditer(str(command or "")):
        literal = match.group(0)
        if literal.startswith("//"):
            continue
        literals.append(literal)
    for match in _RELATIVE_TRAVERSAL_LITERAL_RE.finditer(str(command or "")):
        literals.append(match.group(0))
    try:
        tokens = shlex.split(str(command or ""), posix=True)
    except ValueError:
        tokens = []
    for token in tokens:
        if token in {">", ">>", ">|", "&>", "&>>"} or "://" in token:
            continue
        if token.startswith(("/", "./", "../", "~")) or "/" in token:
            literals.append(token)
    return tuple(literals)


def _shell_write_redirect_targets(command: str) -> tuple[str, ...]:
    try:
        tokens = shlex.split(str(command or ""), posix=True)
    except ValueError:
        return ()
    targets: list[str] = []
    skip_next = False
    for index, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if _WRITE_REDIRECT_TOKEN_RE.match(token):
            if index + 1 < len(tokens):
                targets.append(tokens[index + 1])
                skip_next = True
            continue
        match = _INLINE_WRITE_REDIRECT_RE.match(token)
        if match:
            targets.append(match.group(1))
    return tuple(targets)
