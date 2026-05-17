"""Codex-like provider-visible tool surface."""

from __future__ import annotations

from ..tool_specs import ImplementLaneToolSpec

CODEX_HOT_PATH_PROFILE_ID = "codex_hot_path"

_CODEX_APPLY_PATCH_SPEC = ImplementLaneToolSpec(
    name="apply_patch",
    access="write",
    description=(
        "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, "
        "so do not wrap the patch in JSON."
    ),
    approval_required=True,
    dry_run_supported=True,
    input_transport="json_line_array",
    preferred_bulk_argument="patch_lines",
    fallback_bulk_arguments=("patch", "input"),
    provider_native_input_kind="freeform_apply_patch",
)

_CODEX_EXEC_COMMAND_SPEC = ImplementLaneToolSpec(
    name="exec_command",
    access="execute",
    description="Runs a command, returning output or a command_id for ongoing polling.",
    approval_required=True,
)

_CODEX_WRITE_STDIN_SPEC = ImplementLaneToolSpec(
    name="write_stdin",
    access="execute",
    description=(
        "Poll an existing yielded command by short command_id with empty chars. "
        "Interactive stdin is disabled in this profile version."
    ),
)

_CODEX_LIST_DIR_SPEC = ImplementLaneToolSpec(
    name="list_dir",
    access="read",
    description="List a workspace directory with bounded entries.",
)


def codex_hot_path_tool_specs(*, enable_list_dir: bool) -> tuple[ImplementLaneToolSpec, ...]:
    """Return provider-visible specs for the Codex-like hot path profile."""

    specs = [_CODEX_APPLY_PATCH_SPEC, _CODEX_EXEC_COMMAND_SPEC, _CODEX_WRITE_STDIN_SPEC]
    if enable_list_dir:
        specs.insert(1, _CODEX_LIST_DIR_SPEC)
    return tuple(specs)


__all__ = [
    "CODEX_HOT_PATH_PROFILE_ID",
    "codex_hot_path_tool_specs",
]
