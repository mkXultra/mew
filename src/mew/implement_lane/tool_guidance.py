"""Internal helper logic for implementation-lane tool guidance."""

from __future__ import annotations

import json


def is_hard_runtime_artifact_task(task_contract: object) -> bool:
    """Return whether the task should use the hard-runtime artifact profile."""

    text = _contract_text_for_tool_guidance(task_contract)
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


def _contract_text_for_tool_guidance(task_contract: object) -> str:
    if isinstance(task_contract, str):
        return task_contract.casefold()
    try:
        return json.dumps(task_contract, ensure_ascii=False, sort_keys=True).casefold()
    except TypeError:
        return str(task_contract or "").casefold()


__all__ = [
    "hide_unavailable_write_file_guidance",
    "is_hard_runtime_artifact_task",
]
