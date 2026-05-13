"""Provider-neutral implementation-lane tool policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal

ToolAccess = Literal["read", "write", "execute", "approval", "finish"]
ToolInputTransport = Literal["json_arguments", "json_line_array", "provider_native_freeform"]


@dataclass(frozen=True)
class ImplementLaneToolSpec:
    """Provider-neutral tool shape before provider-specific translation."""

    name: str
    access: ToolAccess
    description: str
    approval_required: bool = False
    dry_run_supported: bool = False
    provider_native_eligible: bool = True
    input_transport: ToolInputTransport = "json_arguments"
    preferred_bulk_argument: str = ""
    fallback_bulk_arguments: tuple[str, ...] = ()
    provider_native_input_kind: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "access": self.access,
            "description": self.description,
            "approval_required": self.approval_required,
            "dry_run_supported": self.dry_run_supported,
            "provider_native_eligible": self.provider_native_eligible,
            "input_transport": self.input_transport,
            "preferred_bulk_argument": self.preferred_bulk_argument,
            "fallback_bulk_arguments": list(self.fallback_bulk_arguments),
            "provider_native_input_kind": self.provider_native_input_kind,
        }


V2_BASE_TOOL_SPECS: tuple[ImplementLaneToolSpec, ...] = (
    ImplementLaneToolSpec(
        name="apply_patch",
        access="write",
        description=(
            "Apply a raw patch to source files. Use this for multi-line edits, new files, "
            "deletions, and renames. Do not wrap custom/freeform patch input in JSON."
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
            "Edit a file with exact replacements or structured hunks. Use when anchors "
            "are precise; ambiguous matches fail closed."
        ),
        approval_required=True,
        dry_run_supported=True,
    ),
    ImplementLaneToolSpec(
        name="write_file",
        access="write",
        description=(
            "Write a small complete file, especially generated non-source output. Prefer "
            "apply_patch or edit_file for source changes and large replacements."
        ),
        approval_required=True,
        dry_run_supported=True,
    ),
    ImplementLaneToolSpec(
        name="run_command",
        access="execute",
        description=(
            "Run a bounded command, build, runtime, or diagnostic through managed exec. "
            "Use source mutation tools for edits. Output returns compact terminal text with refs."
        ),
        approval_required=True,
    ),
    ImplementLaneToolSpec(
        name="run_tests",
        access="execute",
        description=(
            "Run a bounded verifier or test command through managed exec. Output returns compact "
            "terminal text with refs."
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
        description="Read a bounded workspace file excerpt with line anchors.",
    ),
    ImplementLaneToolSpec(
        name="search_text",
        access="read",
        description="Search workspace text and return bounded path:line anchors.",
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
    ImplementLaneToolSpec(
        name="finish",
        access="finish",
        description="Finish only after acceptance evidence is present.",
    ),
)


def list_v2_base_tool_specs() -> tuple[ImplementLaneToolSpec, ...]:
    """Return the default provider-neutral v2 tool surface."""

    return V2_BASE_TOOL_SPECS


def list_v2_tool_specs_for_mode(mode: object) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the tool surface allowed for a v2 permission mode."""

    mode_name = str(mode or "read_only").strip() or "read_only"
    if mode_name in {"read_only", "plan"}:
        return tuple(spec for spec in V2_BASE_TOOL_SPECS if spec.access in {"read", "finish"})
    if mode_name == "exec":
        return tuple(spec for spec in V2_BASE_TOOL_SPECS if spec.access in {"read", "execute", "finish"})
    if mode_name == "write":
        return tuple(spec for spec in V2_BASE_TOOL_SPECS if spec.access in {"read", "write", "finish"})
    if mode_name in {"full", "implement", "implementation"}:
        return V2_BASE_TOOL_SPECS
    return tuple(spec for spec in V2_BASE_TOOL_SPECS if spec.access in {"read", "finish"})


def list_v2_tool_specs_for_task(
    mode: object,
    *,
    task_contract: object = None,
) -> tuple[ImplementLaneToolSpec, ...]:
    """Return the provider-visible v2 tool surface for a task shape."""

    specs = list_v2_tool_specs_for_mode(mode)
    if not is_hard_runtime_artifact_task(task_contract):
        return specs
    return tuple(spec for spec in specs if spec.name != "write_file")


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
