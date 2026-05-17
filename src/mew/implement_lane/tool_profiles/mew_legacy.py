"""Legacy mew provider-visible tool surface."""

from __future__ import annotations

from ..tool_specs import ImplementLaneToolSpec

MEW_LEGACY_PROFILE_ID = "mew_legacy"

MEW_LEGACY_TOOL_SPECS: tuple[ImplementLaneToolSpec, ...] = (
    ImplementLaneToolSpec(
        name="apply_patch",
        access="write",
        description=(
            "Primary source mutation tool for multi-line edits, new files, deletions, "
            "and renames. Use it for the smallest runnable candidate once the target "
            "file or path is known. Do not wrap custom/freeform patch input in JSON."
        ),
        approval_required=True,
        dry_run_supported=True,
        input_transport="json_line_array",
        preferred_bulk_argument="patch_lines",
        fallback_bulk_arguments=("patch", "input"),
        provider_native_input_kind="freeform_apply_patch",
    ),
    ImplementLaneToolSpec(
        name="edit_file",
        access="write",
        description=(
            "Edit a file with exact replacements or structured hunks. Use for focused "
            "source changes when anchors are precise; ambiguous matches fail closed."
        ),
        approval_required=True,
        dry_run_supported=True,
    ),
    ImplementLaneToolSpec(
        name="write_file",
        access="write",
        description=(
            "Write a complete new file when the target path is missing and the full "
            "content is known. Use content_lines for multi-line source. Prefer "
            "apply_patch or edit_file for modifying existing source files."
        ),
        approval_required=True,
        dry_run_supported=True,
    ),
    ImplementLaneToolSpec(
        name="run_command",
        access="execute",
        description=(
            "Run a bounded command, build, runtime, or verifier through managed exec. "
            "Use command output to patch or edit source; commands are not the source editing API. "
            "Output is compact by default; request a larger bounded output budget when terminal text is needed."
        ),
        approval_required=True,
    ),
    ImplementLaneToolSpec(
        name="run_tests",
        access="execute",
        description=(
            "Run a bounded verifier or test command through managed exec. Use failures to patch "
            "or edit source. Output is compact by default; request a larger bounded output budget "
            "when failure text is needed."
        ),
        approval_required=True,
    ),
    ImplementLaneToolSpec(
        name="poll_command",
        access="execute",
        description="Poll a yielded managed command by command_run_id.",
    ),
    ImplementLaneToolSpec(
        name="cancel_command",
        access="execute",
        description="Cancel a yielded managed command by command_run_id.",
    ),
    ImplementLaneToolSpec(
        name="read_command_output",
        access="execute",
        description="Read a bounded slice of managed command spool output.",
    ),
    ImplementLaneToolSpec(
        name="read_file",
        access="read",
        description="Read only the bounded workspace excerpt needed to choose or validate a patch; returns line anchors.",
    ),
    ImplementLaneToolSpec(
        name="search_text",
        access="read",
        description="Find candidate source anchors and return bounded path:line matches.",
    ),
    ImplementLaneToolSpec(
        name="glob",
        access="read",
        description="List workspace paths matching a glob.",
    ),
    ImplementLaneToolSpec(
        name="inspect_dir",
        access="read",
        description="List a workspace directory.",
    ),
    ImplementLaneToolSpec(
        name="git_status",
        access="read",
        description="Inspect git status for an allowed workspace root.",
    ),
    ImplementLaneToolSpec(
        name="git_diff",
        access="read",
        description="Inspect bounded git diff or diffstat for an allowed workspace root.",
    ),
)


def mew_legacy_tool_specs_for_mode(mode: object) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the legacy provider-visible surface allowed for a permission mode."""

    mode_name = str(mode or "read_only").strip() or "read_only"
    if mode_name in {"read_only", "plan"}:
        return tuple(spec for spec in MEW_LEGACY_TOOL_SPECS if spec.access == "read")
    if mode_name == "exec":
        return tuple(spec for spec in MEW_LEGACY_TOOL_SPECS if spec.access in {"read", "execute"})
    if mode_name == "write":
        return tuple(spec for spec in MEW_LEGACY_TOOL_SPECS if spec.access in {"read", "write"})
    if mode_name in {"full", "implement", "implementation"}:
        return MEW_LEGACY_TOOL_SPECS
    return tuple(spec for spec in MEW_LEGACY_TOOL_SPECS if spec.access == "read")


def mew_legacy_tool_specs_for_task(
    mode: object,
    *,
    task_contract: object = None,
) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the legacy provider-visible surface for a task shape."""

    return mew_legacy_tool_specs_for_mode(mode)


__all__ = [
    "MEW_LEGACY_PROFILE_ID",
    "MEW_LEGACY_TOOL_SPECS",
    "mew_legacy_tool_specs_for_mode",
    "mew_legacy_tool_specs_for_task",
]
