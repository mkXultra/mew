"""Provider-neutral implement-lane tool spec types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ToolAccess = Literal["read", "write", "execute", "approval"]
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


__all__ = [
    "ImplementLaneToolSpec",
    "ToolAccess",
    "ToolInputTransport",
]
