"""Provider-neutral implementation-lane tool policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolAccess = Literal["read", "write", "execute", "approval", "finish"]


@dataclass(frozen=True)
class ImplementLaneToolSpec:
    """Provider-neutral tool shape before provider-specific translation."""

    name: str
    access: ToolAccess
    description: str
    approval_required: bool = False
    dry_run_supported: bool = False
    provider_native_eligible: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "access": self.access,
            "description": self.description,
            "approval_required": self.approval_required,
            "dry_run_supported": self.dry_run_supported,
            "provider_native_eligible": self.provider_native_eligible,
        }


V2_BASE_TOOL_SPECS: tuple[ImplementLaneToolSpec, ...] = (
    ImplementLaneToolSpec(
        name="read_file",
        access="read",
        description="Read a workspace file through the existing read substrate.",
    ),
    ImplementLaneToolSpec(
        name="search_text",
        access="read",
        description="Search the workspace through rg-backed discovery.",
    ),
    ImplementLaneToolSpec(
        name="run_command",
        access="execute",
        description="Run a command through managed exec with nonterminal state.",
        approval_required=True,
    ),
    ImplementLaneToolSpec(
        name="write_file",
        access="write",
        description="Write a file through the existing write substrate.",
        approval_required=True,
        dry_run_supported=True,
    ),
    ImplementLaneToolSpec(
        name="edit_file",
        access="write",
        description="Edit a file through the existing edit substrate.",
        approval_required=True,
        dry_run_supported=True,
    ),
    ImplementLaneToolSpec(
        name="apply_patch",
        access="write",
        description="Apply a patch through the existing patch approval path.",
        approval_required=True,
        dry_run_supported=True,
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
        return V2_BASE_TOOL_SPECS
    return tuple(spec for spec in V2_BASE_TOOL_SPECS if spec.access in {"read", "finish"})


__all__ = [
    "ImplementLaneToolSpec",
    "ToolAccess",
    "V2_BASE_TOOL_SPECS",
    "list_v2_base_tool_specs",
    "list_v2_tool_specs_for_mode",
]
