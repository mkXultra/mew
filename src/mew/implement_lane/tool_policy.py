"""Compatibility helpers for implementation-lane tool policy.

Provider-visible tool descriptions/specs are owned by tool profile modules.
This module remains as a compatibility facade plus non-provider-visible helper
logic until the Phase 6C deletion gate.
"""

from __future__ import annotations

import json

from .tool_profiles.mew_legacy import (
    MEW_LEGACY_TOOL_SPECS,
    mew_legacy_tool_specs_for_mode,
    mew_legacy_tool_specs_for_task,
)
from .tool_specs import ImplementLaneToolSpec, ToolAccess, ToolInputTransport

V2_BASE_TOOL_SPECS: tuple[ImplementLaneToolSpec, ...] = MEW_LEGACY_TOOL_SPECS


def list_v2_base_tool_specs() -> tuple[ImplementLaneToolSpec, ...]:
    """Return the default provider-neutral v2 tool surface."""

    return V2_BASE_TOOL_SPECS


def list_v2_tool_specs_for_mode(mode: object) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the tool surface allowed for a v2 permission mode."""

    return mew_legacy_tool_specs_for_mode(mode)


def list_v2_tool_specs_for_task(
    mode: object,
    *,
    task_contract: object = None,
) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the provider-visible v2 tool surface for a task shape."""

    return mew_legacy_tool_specs_for_task(mode, task_contract=task_contract)


def is_hard_runtime_artifact_task(task_contract: object) -> bool:
    """Return whether the task should use the hard-runtime artifact profile."""

    text = _contract_text_for_tool_policy(task_contract)
    if not text:
        return False
    runtime_markers = (
        "vm",
        "emulator",
        "interpreter",
        "elf",
        "binary",
        "cross-compile",
        "cross compile",
        "runtime",
        "node ",
    )
    artifact_markers = (
        "/tmp/",
        "frame",
        "screenshot",
        "image",
        "bmp",
        "stdout",
        "boot",
        "log",
        "socket",
        "pid file",
    )
    source_markers = (
        "provided",
        "source",
        "source code",
        "build",
        "compile",
        "make",
        "project",
        "repository",
    )
    return (
        any(marker in text for marker in runtime_markers)
        and any(marker in text for marker in artifact_markers)
        and any(marker in text for marker in source_markers)
    )


def _contract_text_for_tool_policy(task_contract: object) -> str:
    if isinstance(task_contract, str):
        return task_contract.casefold()
    try:
        return json.dumps(task_contract, ensure_ascii=False, sort_keys=True).casefold()
    except TypeError:
        return str(task_contract or "").casefold()


def hide_unavailable_write_file_guidance(text: str) -> str:
    """Remove positive write_file guidance when the tool is not available."""

    replacements = (
        ("write_file, edit_file, or apply_patch", "edit_file or apply_patch"),
        ("write_file/edit_file/apply_patch", "edit_file/apply_patch"),
        ("write_file/edit_file", "edit_file"),
        ("provider-native write_file/content_lines JSON payload", "provider-native JSON payload"),
        ("provider-native write_file payload", "provider-native JSON payload"),
        ("write_file/content_lines JSON payload", "JSON payload"),
        ("write_file overwrite", "overwrite"),
        ("write_file target", "write target"),
        ("write_file", "write tool"),
    )
    value = str(text)
    for old, new in replacements:
        value = value.replace(old, new)
    return value


__all__ = [
    "ImplementLaneToolSpec",
    "ToolAccess",
    "ToolInputTransport",
    "V2_BASE_TOOL_SPECS",
    "hide_unavailable_write_file_guidance",
    "is_hard_runtime_artifact_task",
    "list_v2_base_tool_specs",
    "list_v2_tool_specs_for_mode",
    "list_v2_tool_specs_for_task",
]
