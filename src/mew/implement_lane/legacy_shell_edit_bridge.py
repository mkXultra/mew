"""Narrow legacy shell-edit bridges for implement_v2.

This module is intentionally tiny. It is not a shell source-mutation
classifier; it only recognizes documented compatibility bridges and hands the
actual mutation to the typed write runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import shlex
from pathlib import Path

from ..acceptance_evidence import split_unquoted_shell_command_segments
from .shell_metadata import COMMAND_CLASSIFICATION_SCHEMA_VERSION
from .types import ToolCallEnvelope, ToolResultEnvelope
from .write_runtime import ImplementV2WriteRuntime

BRIDGE_REGISTRY_SCHEMA_VERSION = 1
SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID = "shell_invoked_apply_patch"

_APPLY_PATCH_HEREDOC_RE = re.compile(
    r"\A[ \t]*(?:command[ \t]+)?apply_patch[ \t]+<<(?P<quote>['\"])(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)[ \t]*\n(?P<body>.*)\n(?P=delimiter)[ \t]*\Z",
    re.DOTALL,
)
_APPLY_PATCH_COMMAND_PREFIX_RE = re.compile(r"\A[ \t]*(?:command[ \t]+)?apply_patch(?:[ \t\r\n]|$)")
_APPLY_PATCH_COMMAND_SEGMENT_FALLBACK_RE = re.compile(
    r"(?:\A|[;&|][ \t\r\n]*)(?:[^ \t\r\n;&|]+/)?apply_patch(?:[ \t\r\n]|$)"
)
_HEREDOC_START_RE = re.compile(r"<<-?[ \t]*(?P<quote>['\"]?)(?P<delimiter>[A-Za-z_][A-Za-z0-9_]*)"
                               r"(?P=quote)")


@dataclass(frozen=True)
class LegacyShellEditBridgeMatch:
    bridge_id: str
    effective_tool: str
    arguments: dict[str, object]
    command_classification: dict[str, object]


def bridge_registry_manifest() -> dict[str, object]:
    """Return the bootstrap bridge registry manifest."""

    return {
        "schema_version": BRIDGE_REGISTRY_SCHEMA_VERSION,
        "bridges": [
            {
                "id": SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID,
                "declared_tool": "run_command",
                "effective_tool": "apply_patch",
                "parser_required": "simple",
                "exact_diff_required": True,
                "status": "bootstrap_only",
                "removal_criteria": "delete once provider-native apply_patch calls no longer regress to run_command",
            }
        ],
    }


def bridge_registry_ids() -> tuple[str, ...]:
    manifest = bridge_registry_manifest()
    bridges = manifest.get("bridges") if isinstance(manifest, dict) else []
    return tuple(str(item.get("id") or "") for item in bridges if isinstance(item, dict) and item.get("id"))


def maybe_execute_legacy_shell_edit_bridge(
    call: ToolCallEnvelope,
    *,
    workspace: Path,
    allowed_write_roots: tuple[str, ...],
    approved_write_calls: tuple[object, ...],
    auto_approve_writes: bool,
    allow_governance_writes: bool,
    artifact_dir: object | None,
    parser_available: bool = True,
) -> ToolResultEnvelope | None:
    """Return a bridged result for recognized legacy shell edits.

    ``None`` means the command is not a bridge candidate and normal process
    execution should continue. A non-``None`` result never executes the
    original shell command.
    """

    if call.tool_name != "run_command":
        return None
    candidate = _candidate_kind(call.arguments)
    if not candidate:
        return None
    match = _match_shell_invoked_apply_patch(call.arguments, parser_available=parser_available)
    if match is None:
        return _bridge_invalid_result(
            call,
            reason="legacy shell edit bridge preconditions failed; use apply_patch, edit_file, or write_file",
            failure_subclass="legacy_shell_edit_bridge_precondition_failed",
            command_classification=_bridge_unavailable_classification(
                call.arguments,
                reason="parser_not_installed" if not parser_available else "not_exact_shell_invoked_apply_patch",
            ),
        )
    if not allowed_write_roots:
        return _bridge_invalid_result(
            call,
            reason="legacy shell edit bridge requires an allowed write root; use apply_patch with write approval",
            failure_subclass="legacy_shell_edit_bridge_write_policy_unavailable",
            command_classification=match.command_classification,
        )
    approvals = tuple(approved_write_calls)
    if auto_approve_writes:
        approvals = (
            *approvals,
            {
                "status": "approved",
                "provider_call_id": call.provider_call_id,
                "mew_tool_call_id": call.mew_tool_call_id,
                "source": "legacy_shell_edit_bridge.auto_approve_writes",
                "approval_id": call.provider_call_id or call.mew_tool_call_id,
            },
        )
    write_runtime = ImplementV2WriteRuntime(
        workspace=workspace,
        allowed_write_roots=allowed_write_roots,
        approved_write_calls=approvals,
        allow_governance_writes=allow_governance_writes,
        artifact_dir=artifact_dir,
    )
    write_call = ToolCallEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider=call.provider,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=match.effective_tool,
        arguments=match.arguments,
        provider_message_id=call.provider_message_id,
        turn_index=call.turn_index,
        sequence_index=call.sequence_index,
        raw_arguments_ref=call.raw_arguments_ref,
        received_at=call.received_at,
        status=call.status,
    )
    write_result = write_runtime.execute(write_call)
    return _bridge_result_from_write_result(call, write_result, match=match)


def _candidate_kind(arguments: dict[str, object]) -> str:
    command = str(arguments.get("command") or arguments.get("cmd") or "").strip()
    argv = arguments.get("argv")
    if isinstance(argv, list) and argv:
        first = Path(str(argv[0] or "")).name
        if first == "apply_patch":
            return "argv_apply_patch"
    if _command_segment_invokes_apply_patch(command):
        return "command_apply_patch"
    return ""


def _command_segment_invokes_apply_patch(command: str) -> bool:
    text = _without_heredoc_bodies(str(command or ""))
    if not text.strip():
        return False
    for segment in split_unquoted_shell_command_segments(text):
        if _segment_command_basename(segment) == "apply_patch":
            return True
    return _APPLY_PATCH_COMMAND_SEGMENT_FALLBACK_RE.search(text) is not None


def _without_heredoc_bodies(text: str) -> str:
    lines = str(text or "").splitlines()
    if not lines:
        return ""
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        match = _HEREDOC_START_RE.search(line)
        if match is None:
            index += 1
            continue
        delimiter = str(match.group("delimiter") or "")
        index += 1
        while index < len(lines) and lines[index].strip() != delimiter:
            index += 1
        if index < len(lines):
            kept.append(lines[index])
            index += 1
    return "\n".join(kept)


def _segment_command_basename(segment: str) -> str:
    try:
        tokens = shlex.split(str(segment or ""), posix=True)
    except ValueError:
        return ""
    index = 0
    while index < len(tokens) and tokens[index] in {"(", "{", "then", "do"}:
        index += 1
    while index < len(tokens) and _looks_like_env_assignment(tokens[index]):
        index += 1
    if index < len(tokens) and Path(tokens[index]).name == "env":
        index = _skip_env_wrapper(tokens, index + 1)
    if index < len(tokens) and tokens[index] == "command":
        index += 1
    if index >= len(tokens):
        return ""
    return Path(tokens[index]).name


def _skip_env_wrapper(tokens: list[str], index: int) -> int:
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token in {"-u", "--unset", "-C", "-S"}:
            index += 2
            continue
        if token.startswith("-u") and len(token) > 2:
            index += 1
            continue
        if token.startswith("--unset=") or token.startswith("-C") or token.startswith("-S"):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if _looks_like_env_assignment(token):
            index += 1
            continue
        return index
    return index


def _looks_like_env_assignment(token: str) -> bool:
    name, separator, _value = str(token or "").partition("=")
    return bool(separator and name and name.replace("_", "A").isalnum() and not name[0].isdigit())


def _match_shell_invoked_apply_patch(
    arguments: dict[str, object],
    *,
    parser_available: bool,
) -> LegacyShellEditBridgeMatch | None:
    if not parser_available:
        return None
    patch_text = _patch_text_from_legacy_arguments(arguments)
    command = str(arguments.get("command") or arguments.get("cmd") or "").strip()
    argv = arguments.get("argv")
    if patch_text:
        if isinstance(argv, list):
            argv_parts = [str(part) for part in argv if str(part)]
            if len(argv_parts) == 1 and Path(argv_parts[0]).name == "apply_patch":
                return _bridge_match(arguments, patch_text, reason="argv_apply_patch_with_structured_patch_body")
        if command in {"apply_patch", "command apply_patch"}:
            return _bridge_match(arguments, patch_text, reason="command_apply_patch_with_structured_patch_body")
    match = _APPLY_PATCH_HEREDOC_RE.match(command)
    if match is None:
        return None
    return _bridge_match(arguments, str(match.group("body") or ""), reason="quoted_apply_patch_heredoc")


def _bridge_match(arguments: dict[str, object], patch_text: str, *, reason: str) -> LegacyShellEditBridgeMatch:
    return LegacyShellEditBridgeMatch(
        bridge_id=SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID,
        effective_tool="apply_patch",
        arguments={"patch": patch_text, "apply": True, "dry_run": False},
        command_classification=_bridge_simple_classification(arguments, reason=reason),
    )


def _patch_text_from_legacy_arguments(arguments: dict[str, object]) -> str:
    raw_lines = arguments.get("patch_lines")
    if isinstance(raw_lines, list) and all(isinstance(line, str) for line in raw_lines):
        return "\n".join(raw_lines) + ("\n" if raw_lines else "")
    for key in ("patch", "input"):
        if key in arguments and arguments.get(key) is not None:
            return str(arguments.get(key) or "")
    return ""


def _bridge_result_from_write_result(
    call: ToolCallEnvelope,
    write_result: ToolResultEnvelope,
    *,
    match: LegacyShellEditBridgeMatch,
) -> ToolResultEnvelope:
    first = write_result.content[0] if write_result.content and isinstance(write_result.content[0], dict) else {}
    payload = dict(first)
    applied = write_result.status == "completed" and not write_result.is_error and bool(payload.get("written"))
    payload.update(
        {
            "bridge_registry_id": match.bridge_id,
            "bridge_registry_manifest": bridge_registry_manifest(),
            "bridge_status": "applied" if applied else "rejected",
            "declared_tool": call.tool_name,
            "effective_tool": match.effective_tool,
            "effective_tool_name": match.effective_tool,
            "command_classification": match.command_classification,
            "typed_evidence_refs": list(write_result.evidence_refs),
        }
    )
    if not applied:
        payload.setdefault("tool_route", "invalid_tool_contract")
        payload.setdefault("failure_class", "tool_contract_misuse")
        payload.setdefault("failure_subclass", "legacy_shell_edit_bridge_typed_mutation_failed")
        payload["suggested_tool"] = "apply_patch|edit_file|write_file"
        payload["suggested_next_action"] = "use apply_patch, edit_file, or write_file directly"
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status=write_result.status,
        is_error=write_result.is_error,
        content=(payload,),
        content_refs=write_result.content_refs,
        evidence_refs=write_result.evidence_refs,
        side_effects=write_result.side_effects,
        started_at=write_result.started_at,
        finished_at=write_result.finished_at,
    )


def _bridge_invalid_result(
    call: ToolCallEnvelope,
    *,
    reason: str,
    failure_subclass: str,
    command_classification: dict[str, object],
) -> ToolResultEnvelope:
    payload = {
        "tool_route": "invalid_tool_contract",
        "declared_tool": call.tool_name,
        "effective_tool": "none",
        "bridge_registry_id": SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID,
        "bridge_registry_manifest": bridge_registry_manifest(),
        "bridge_status": "rejected",
        "failure_class": "tool_contract_misuse",
        "failure_subclass": failure_subclass,
        "reason": reason,
        "recoverable": True,
        "recoverable_tool_contract_misuse": True,
        "tool_contract_recovery_eligible": False,
        "terminal_failure_reaction_eligible": False,
        "preserved_command_hash": _command_hash(_command_identity(call.arguments)),
        "suggested_tool": "apply_patch|edit_file|write_file",
        "suggested_next_action": "use apply_patch, edit_file, or write_file directly; do not execute shell edits",
        "suggested_use_shell": False,
        "command_classification": command_classification,
    }
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="failed",
        is_error=True,
        content=(payload,),
    )


def _bridge_simple_classification(arguments: dict[str, object], *, reason: str) -> dict[str, object]:
    return {
        "schema_version": COMMAND_CLASSIFICATION_SCHEMA_VERSION,
        "result": "simple",
        "parser": "legacy_shell_edit_bridge",
        "reason": reason,
        "command_hash": _command_hash(_command_identity(arguments)),
        "features": {
            "base_commands": ["apply_patch"],
            "bridge_registry_id": SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID,
            "exact_diff_required": True,
            "has_redirection": reason == "quoted_apply_patch_heredoc",
            "has_shell_expansion": False,
            "explicit_shell_interpreter": False,
            "read_search_list_hint": "unknown",
            "process_lifecycle_hint": "foreground",
        },
        "not_source_mutation_classifier": True,
        "shortcut_consumers_enabled": True,
    }


def _bridge_unavailable_classification(arguments: dict[str, object], *, reason: str) -> dict[str, object]:
    return {
        "schema_version": COMMAND_CLASSIFICATION_SCHEMA_VERSION,
        "result": "unavailable" if reason == "parser_not_installed" else "too_complex",
        "parser": "legacy_shell_edit_bridge" if reason != "parser_not_installed" else "none",
        "reason": reason,
        "command_hash": _command_hash(_command_identity(arguments)),
        "features": {
            "base_commands": ["apply_patch"],
            "bridge_registry_id": SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID,
        },
        "not_source_mutation_classifier": True,
        "shortcut_consumers_enabled": False,
    }


def _command_identity(arguments: dict[str, object]) -> str:
    if isinstance(arguments.get("argv"), list):
        return "argv:" + repr([str(part) for part in arguments.get("argv") or []])
    return str(arguments.get("command") or arguments.get("cmd") or "")


def _command_hash(command: object) -> str:
    return "sha256:" + hashlib.sha256(str(command or "").encode("utf-8", errors="replace")).hexdigest()


__all__ = [
    "SHELL_INVOKED_APPLY_PATCH_BRIDGE_ID",
    "bridge_registry_ids",
    "bridge_registry_manifest",
    "maybe_execute_legacy_shell_edit_bridge",
]
