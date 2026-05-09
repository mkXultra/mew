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

from .types import ImplementLaneInput, ToolCallEnvelope, ToolResultEnvelope
from .v2_runtime import (
    IMPLEMENT_V2_LANE,
    _first_write_readiness_from_trace,
    _provider_visible_tool_result_for_history,
    run_fake_exec_implement_v2,
)

TOOL_LAB_SCHEMA_VERSION = 1
_ABSOLUTE_PATH_LITERAL_RE = re.compile(r"(?<![:\w./-])/(?:[^\s'\";|&<>`$(){},]+)")
_RELATIVE_TRAVERSAL_LITERAL_RE = re.compile(r"(?<![\w./-])(?:\.\./)+(?:[^\s'\";|&<>`$(){},]+)")
_WRITE_REDIRECT_TOKEN_RE = re.compile(r"^(?:\d?>>?|&>>?|>\|?)$")
_INLINE_WRITE_REDIRECT_RE = re.compile(r"^(?:\d?>>?|&>>?|>\|?)(.+)$")


def analyze_implement_v2_tool_lab_artifact(
    path: object,
    *,
    workspace: object = "",
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
    scope_error = _tool_lab_command_scope_error(
        command,
        workspace_path=workspace_path,
        write_roots=write_roots,
    )
    if scope_error:
        raise ValueError(scope_error)
    lane_input = ImplementLaneInput(
        work_session_id="tool-lab",
        task_id="tool-lab",
        workspace=str(workspace_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"goal": "implement_v2 tool-lab deterministic command diagnostic"},
        lane_config={
            "mode": "exec",
            "allowed_read_roots": list(read_roots),
            "allowed_write_roots": list(write_roots),
            "allow_shell": True,
            "first_write_probe_threshold": int(probe_threshold or 3),
        },
    )
    arguments: dict[str, object] = {
        "command": str(command),
        "cwd": str(cwd or "."),
        "command_intent": str(command_intent or "probe"),
    }
    if timeout is not None:
        arguments["timeout"] = float(timeout)
    result = run_fake_exec_implement_v2(
        lane_input,
        provider_calls=(
            {
                "id": "tool-lab-command",
                "name": "run_command",
                "arguments": arguments,
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "tool-lab command executed"},
    )
    manifest = dict((result.updated_lane_state or {}).get("proof_manifest") or {})
    analysis = analyze_implement_v2_tool_lab_manifest(
        manifest,
        manifest_path="",
        workspace=workspace,
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
    analysis["result_status"] = result.status
    analysis["result_metrics"] = dict(result.metrics or {})
    return analysis


def analyze_implement_v2_tool_lab_manifest(
    manifest: dict[str, object],
    *,
    manifest_path: str = "",
    workspace: object = "",
    target_paths: tuple[str, ...] | list[str] = (),
    probe_threshold: int | None = None,
    requires_deep_runtime_coverage: bool = False,
) -> dict[str, object]:
    tool_calls = tuple(_tool_call_from_dict(item) for item in _list_of_dicts(manifest.get("tool_calls")))
    tool_results = tuple(_tool_result_from_dict(item) for item in _list_of_dicts(manifest.get("tool_results")))
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    mutations = _collect_source_tree_mutations(tool_results)
    suspicious = _suspicious_source_tree_mutations(mutations, workspace=workspace)
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
            target_paths=tuple(target_paths),
        )
        recomputed_readiness = _first_write_readiness_from_trace(
            active_work_todo,
            tool_calls=tool_calls,
            tool_results=trusted_tool_results,
            probe_threshold=int(probe_threshold or observed_readiness.get("probe_threshold") or 3),
            requires_deep_runtime_coverage=requires_deep_runtime_coverage,
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
            if effect.get("kind") == "source_tree_mutation" and isinstance(effect.get("record"), dict):
                records.append(dict(effect["record"]))
        if not records:
            for content in result.content:
                if not isinstance(content, dict) or not isinstance(content.get("source_tree_mutations"), list):
                    continue
                records.extend(dict(item) for item in content["source_tree_mutations"] if isinstance(item, dict))
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
                    }
                )
    return mutations


def _tool_results_with_trusted_source_mutations(
    results: tuple[ToolResultEnvelope, ...],
    *,
    workspace: object,
    target_paths: tuple[str, ...],
) -> tuple[ToolResultEnvelope, ...]:
    return tuple(
        replace(
            result,
            content=_content_with_trusted_source_mutations(result.content, workspace=workspace, target_paths=target_paths),
            side_effects=_side_effects_with_trusted_source_mutations(
                result.side_effects,
                workspace=workspace,
                target_paths=target_paths,
            ),
        )
        for result in results
    )


def _side_effects_with_trusted_source_mutations(
    effects: tuple[dict[str, object], ...],
    *,
    workspace: object,
    target_paths: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    trusted: list[dict[str, object]] = []
    for effect in effects:
        if effect.get("kind") != "source_tree_mutation" or not isinstance(effect.get("record"), dict):
            trusted.append(dict(effect))
            continue
        record = _trusted_source_mutation_record(dict(effect["record"]), workspace=workspace, target_paths=target_paths)
        if record:
            trusted.append({**effect, "record": record})
    return tuple(trusted)


def _content_with_trusted_source_mutations(
    content_items: tuple[object, ...],
    *,
    workspace: object,
    target_paths: tuple[str, ...],
) -> tuple[object, ...]:
    trusted_items: list[object] = []
    for item in content_items:
        if not isinstance(item, dict) or not isinstance(item.get("source_tree_mutations"), list):
            trusted_items.append(item)
            continue
        copied = dict(item)
        trusted_records = []
        for record in copied.get("source_tree_mutations") or []:
            if isinstance(record, dict):
                trusted_record = _trusted_source_mutation_record(record, workspace=workspace, target_paths=target_paths)
                if trusted_record:
                    trusted_records.append(trusted_record)
        copied["source_tree_mutations"] = trusted_records
        trusted_items.append(copied)
    return tuple(trusted_items)


def _trusted_source_mutation_record(
    record: dict[str, object],
    *,
    workspace: object,
    target_paths: tuple[str, ...],
) -> dict[str, object]:
    changes = [
        change
        for change in _list_of_dicts(record.get("changes"))
        if _trusted_source_mutation_path(str(change.get("path") or ""), workspace=workspace, target_paths=target_paths)
    ]
    if not changes:
        return {}
    return {**record, "changed_count": len(changes), "changes": changes}


def _trusted_source_mutation_path(path: str, *, workspace: object, target_paths: tuple[str, ...]) -> bool:
    workspace_path = Path(str(workspace)).expanduser().resolve(strict=False) if str(workspace or "").strip() else None
    if _suspicious_mutation_reason(path, workspace_path=workspace_path):
        return False
    if not target_paths:
        return True
    candidate = _candidate_path(path, workspace_path=workspace_path)
    return any(_path_matches_target(candidate, target, workspace_path=workspace_path) for target in target_paths)


def _suspicious_source_tree_mutations(
    mutations: list[dict[str, object]],
    *,
    workspace: object,
) -> list[dict[str, object]]:
    workspace_path = Path(str(workspace)).expanduser().resolve(strict=False) if str(workspace or "").strip() else None
    suspicious: list[dict[str, object]] = []
    for mutation in mutations:
        path = str(mutation.get("path") or "")
        reason = _suspicious_mutation_reason(path, workspace_path=workspace_path)
        if not reason:
            continue
        suspicious.append({**mutation, "reason": reason})
    return suspicious


def _suspicious_mutation_reason(path: str, *, workspace_path: Path | None) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return "empty_path"
    if workspace_path is not None:
        try:
            candidate = _candidate_path(normalized, workspace_path=workspace_path)
        except OSError:
            return ""
        if candidate != workspace_path and not _is_relative_to(candidate, workspace_path):
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
