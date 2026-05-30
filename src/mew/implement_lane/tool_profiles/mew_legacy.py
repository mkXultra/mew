"""Legacy mew provider-visible tool surface."""

from __future__ import annotations

from ...prompt_sections import (
    CACHE_POLICY_CACHEABLE,
    CACHE_POLICY_SESSION,
    STABILITY_SEMI_STATIC,
    STABILITY_STATIC,
    PromptSection,
)
from ..tool_specs import ImplementLaneToolSpec

MEW_LEGACY_PROFILE_ID = "mew_legacy"
MEW_LEGACY_PROMPT_CONTRACT_ID = "mew_legacy_prompt_v1"

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


def list_v2_base_tool_specs() -> tuple[ImplementLaneToolSpec, ...]:
    """Return the legacy default provider-neutral v2 tool surface."""

    return MEW_LEGACY_TOOL_SPECS


def list_v2_tool_specs_for_mode(mode: object) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the legacy tool surface allowed for a v2 permission mode."""

    return mew_legacy_tool_specs_for_mode(mode)


def list_v2_tool_specs_for_task(
    mode: object,
    *,
    task_contract: object = None,
) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the legacy provider-visible v2 tool surface for a task shape."""

    return mew_legacy_tool_specs_for_task(mode, task_contract=task_contract)


def mew_legacy_tool_specs_for_task(
    mode: object,
    *,
    task_contract: object = None,
) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the legacy provider-visible surface for a task shape."""

    return mew_legacy_tool_specs_for_mode(mode)


def mew_legacy_prompt_sections(
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...],
    task_contract_content: str,
) -> tuple[PromptSection, ...]:
    """Return the legacy provider-visible prompt contract."""

    tool_names = {spec.name for spec in tool_specs}
    if {"apply_patch", "edit_file"} & tool_names and "write_file" in tool_names:
        mutation_sentence = (
            "Create complete new files with write_file when the target path is missing; "
            "modify existing source with apply_patch or edit_file. "
        )
    elif {"apply_patch", "edit_file"} & tool_names:
        mutation_sentence = "Make source changes with apply_patch or edit_file. "
    else:
        mutation_sentence = "Use the available read-only tools to inspect repository state. "
    if {"run_command", "run_tests"} & tool_names:
        verify_sentence = "Use run_command or run_tests to build, run, and verify. "
    else:
        verify_sentence = "Use available observations to support the final response. "
    coding_contract_content = (
        "Inspect only enough context to choose a minimal runnable candidate. "
        f"{mutation_sentence}"
        f"{verify_sentence}"
        "When the task asks for a new file or artifact and the target path is known, "
        "create the smallest runnable version early, then run it and repair from concrete failures. "
        "If the task or verify command names a missing source or artifact path, "
        "treat that as the target path and create the smallest runnable file before extended reverse engineering. "
        "If task_facts.missing_workspace_paths is present, use those factual missing paths as target-path context; "
        "prefer a minimal runnable artifact at the named path over extended archaeology. "
        "Treat task_facts.existing_workspace_paths as provided inputs or references, not replacement deliverables; "
        "do not rebuild or substitute provided artifacts unless the task explicitly asks for that rebuild. "
        "Repair from the latest concrete failure shown in the transcript. "
        "When no further tool action is useful, provide a concise final response."
    )
    return (
        _lane_base_section(),
        _tool_contract_section(),
        PromptSection(
            id="implement_v2_coding_contract",
            version="v2",
            title="Implement V2 Coding Contract",
            content=coding_contract_content,
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_task_contract",
            version="v0",
            title="Implement V2 Task Contract",
            content=task_contract_content,
            stability=STABILITY_SEMI_STATIC,
            cache_policy=CACHE_POLICY_SESSION,
            profile="implement_v2",
        ),
    )


def _lane_base_section() -> PromptSection:
    return PromptSection(
        id="implement_v2_lane_base",
        version="v0",
        title="Implement V2 Lane Base",
        content=(
            "You are implementing in a repository through native tool calls. "
            "Use the provider-native transcript as the live history, preserve "
            "paired tool results, and continue until the requested implementation is complete."
        ),
        stability=STABILITY_STATIC,
        cache_policy=CACHE_POLICY_CACHEABLE,
        profile="implement_v2",
    )


def _tool_contract_section() -> PromptSection:
    return PromptSection(
        id="implement_v2_tool_contract",
        version="v0",
        title="Implement V2 Tool Contract",
        content=(
            "Every provider tool call must receive exactly one paired tool result. "
            "Unknown, invalid, denied, interrupted, or failed calls still receive "
            "model-visible results. Running/yielded command states are content "
            "inside normal tool results, not provider protocol states."
        ),
        stability=STABILITY_STATIC,
        cache_policy=CACHE_POLICY_CACHEABLE,
        profile="implement_v2",
    )


__all__ = [
    "MEW_LEGACY_PROFILE_ID",
    "MEW_LEGACY_PROMPT_CONTRACT_ID",
    "MEW_LEGACY_TOOL_SPECS",
    "list_v2_base_tool_specs",
    "list_v2_tool_specs_for_mode",
    "list_v2_tool_specs_for_task",
    "mew_legacy_prompt_sections",
    "mew_legacy_tool_specs_for_mode",
    "mew_legacy_tool_specs_for_task",
]
