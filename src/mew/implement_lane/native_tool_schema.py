"""Provider-native Responses tool schema lowering for implement_v2.

This module is Phase 2 substrate only.  It translates the existing
provider-neutral ``ImplementLaneToolSpec`` objects into Responses-compatible
tool descriptors and records strict-schema decisions for offline review.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json

from .tool_policy import ImplementLaneToolSpec

NATIVE_TOOL_SCHEMA_VERSION = 1

APPLY_PATCH_LARK_GRAMMAR = """start: begin_patch hunk+ end_patch
begin_patch: "*** Begin Patch" LF
end_patch: "*** End Patch" LF?

hunk: add_hunk | delete_hunk | update_hunk
add_hunk: "*** Add File: " filename LF add_line+
delete_hunk: "*** Delete File: " filename LF
update_hunk: "*** Update File: " filename LF change_move? change?

filename: /(.+)/
add_line: "+" /(.*)/ LF -> line

change_move: "*** Move to: " filename LF
change: (change_context | change_line)+ eof_line?
change_context: ("@@" | "@@ " /(.+)/) LF
change_line: ("+" | "-" | " ") /(.*)/ LF
eof_line: "*** End of File" LF

%import common.LF
"""


@dataclass(frozen=True)
class NativeToolSchemaCapabilities:
    """Provider capabilities that affect tool schema lowering."""

    supports_custom_freeform_tools: bool = True
    supports_json_schema_strict: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "supports_custom_freeform_tools": self.supports_custom_freeform_tools,
            "supports_json_schema_strict": self.supports_json_schema_strict,
        }


@dataclass(frozen=True)
class StrictSchemaValidationResult:
    """Offline strict-schema validation result."""

    valid: bool
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"valid": self.valid, "errors": list(self.errors)}


@dataclass(frozen=True)
class LoweredNativeToolSpec:
    """One Responses tool descriptor plus lowering metadata."""

    name: str
    provider_tool: dict[str, object]
    provider_tool_kind: str
    strict: bool | None
    strict_false_reason: str = ""
    validation: StrictSchemaValidationResult = StrictSchemaValidationResult(True)

    def as_descriptor_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "provider_tool_kind": self.provider_tool_kind,
            "tool_spec_hash": stable_json_hash(self.provider_tool),
            "strict": self.strict,
            "validation": self.validation.as_dict(),
        }
        if self.strict_false_reason:
            payload["strict_false_reason"] = self.strict_false_reason
        return payload


def lower_implement_lane_tool_specs(
    tool_specs: Iterable[ImplementLaneToolSpec],
    *,
    capabilities: NativeToolSchemaCapabilities | None = None,
) -> tuple[LoweredNativeToolSpec, ...]:
    """Lower provider-neutral tool specs into Responses tool descriptors."""

    caps = capabilities or NativeToolSchemaCapabilities()
    return tuple(
        lower_implement_lane_tool_spec(spec, capabilities=caps) for spec in tool_specs
    )


def lower_implement_lane_tool_spec(
    spec: ImplementLaneToolSpec,
    *,
    capabilities: NativeToolSchemaCapabilities | None = None,
) -> LoweredNativeToolSpec:
    """Lower one provider-neutral tool spec into a Responses tool descriptor."""

    caps = capabilities or NativeToolSchemaCapabilities()
    if not spec.provider_native_eligible:
        schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        return _function_tool(
            spec,
            schema,
            strict=False,
            strict_false_reason="provider_native_eligible=false",
            validation=StrictSchemaValidationResult(
                False, ("provider_native_eligible=false",)
            ),
        )

    if (
        spec.name == "apply_patch"
        and spec.provider_native_input_kind == "freeform_apply_patch"
    ):
        if caps.supports_custom_freeform_tools:
            return LoweredNativeToolSpec(
                name=spec.name,
                provider_tool={
                    "type": "custom",
                    "name": "apply_patch",
                    "description": (
                        "Apply a raw patch to source files. Use this for multi-line edits, new files, "
                        "deletions, and renames. Do not wrap custom/freeform patch input in JSON."
                    ),
                    "format": {
                        "type": "grammar",
                        "syntax": "lark",
                        "definition": APPLY_PATCH_LARK_GRAMMAR,
                    },
                },
                provider_tool_kind="custom",
                strict=None,
            )
        schema = _apply_patch_json_fallback_schema()
        return _function_tool(
            spec,
            schema,
            strict=False,
            strict_false_reason="custom_freeform_apply_patch_not_supported",
            validation=validate_strict_json_schema(schema),
        )

    schema = structured_tool_json_schema(spec.name)
    if schema is None:
        fallback_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        return _function_tool(
            spec,
            fallback_schema,
            strict=False,
            strict_false_reason=f"no_strict_schema_for_tool:{spec.name}",
            validation=StrictSchemaValidationResult(
                False, (f"no_strict_schema_for_tool:{spec.name}",)
            ),
        )

    validation = validate_strict_json_schema(schema)
    strict = caps.supports_json_schema_strict and validation.valid
    strict_false_reason = ""
    if not caps.supports_json_schema_strict:
        strict_false_reason = "provider_json_schema_strict_not_supported"
    elif not validation.valid:
        strict_false_reason = "strict_schema_invalid:" + ",".join(validation.errors)
    return _function_tool(
        spec,
        schema,
        strict=strict,
        strict_false_reason=strict_false_reason,
        validation=validation,
    )


def validate_strict_json_schema(
    schema: Mapping[str, object],
) -> StrictSchemaValidationResult:
    """Validate the strict subset required by Responses function tools.

    A strict object schema must require every declared property and must reject
    additional properties.  The same rule is applied recursively to nested
    object schemas.
    """

    errors: list[str] = []
    _validate_strict_node(schema, path="$", errors=errors)
    return StrictSchemaValidationResult(valid=not errors, errors=tuple(errors))


def provider_tool_spec_hash(lowered_tools: Iterable[LoweredNativeToolSpec]) -> str:
    """Return a stable hash for the provider-visible tool descriptors."""

    return stable_json_hash([tool.provider_tool for tool in lowered_tools])


def provider_tool_specs(
    lowered_tools: Iterable[LoweredNativeToolSpec],
) -> tuple[dict[str, object], ...]:
    """Return provider-visible tool descriptors from lowered metadata."""

    return tuple(tool.provider_tool for tool in lowered_tools)


def strict_false_reasons(
    lowered_tools: Iterable[LoweredNativeToolSpec],
) -> dict[str, str]:
    """Return strict=false reasons keyed by tool name."""

    return {
        tool.name: tool.strict_false_reason
        for tool in lowered_tools
        if tool.strict is False and tool.strict_false_reason
    }


def lowered_tool_descriptor_metadata(
    lowered_tools: Iterable[LoweredNativeToolSpec],
) -> tuple[dict[str, object], ...]:
    """Return audit metadata for request descriptors."""

    return tuple(tool.as_descriptor_metadata() for tool in lowered_tools)


def structured_tool_json_schema(tool_name: str) -> dict[str, object] | None:
    """Return the Phase 2 strict JSON schema for a structured implement_v2 tool."""

    schemas: dict[str, dict[str, object]] = {
        "inspect_dir": _strict_object(
            {
                "path": _string("Workspace-relative directory path to inspect."),
                "max_entries": _nullable_integer(
                    "Maximum directory entries to return."
                ),
            }
        ),
        "read_file": _strict_object(
            {
                "path": _string("Workspace-relative path to read."),
                "offset": _nullable_integer("Character offset to start reading from."),
                "max_chars": _nullable_integer("Maximum characters to return."),
            }
        ),
        "search_text": _strict_object(
            {
                "query": _string("Text or regular expression to search for."),
                "path": _nullable_string("Workspace-relative file or directory scope."),
                "max_results": _nullable_integer("Maximum matching records to return."),
                "context_lines": _nullable_integer(
                    "Context lines to include around each match."
                ),
            }
        ),
        "glob": _strict_object(
            {
                "pattern": _string("Glob pattern to match."),
                "path": _nullable_string("Workspace-relative directory scope."),
                "max_results": _nullable_integer("Maximum paths to return."),
            }
        ),
        "git_status": _strict_object(
            {
                "path": _nullable_string(
                    "Workspace-relative repository root or scope."
                ),
            }
        ),
        "git_diff": _strict_object(
            {
                "path": _nullable_string(
                    "Workspace-relative repository root or scope."
                ),
                "cached": _nullable_boolean("Whether to inspect staged changes."),
                "stat": _nullable_boolean(
                    "Whether to return diffstat instead of full diff."
                ),
                "max_chars": _nullable_integer("Maximum diff characters to return."),
            }
        ),
        "run_command": _command_schema(),
        "run_tests": _command_schema(),
        "poll_command": _strict_object(
            {
                "command_run_id": _string("Managed command run id to poll."),
                "max_output_chars": _nullable_integer(
                    "Optional provider-visible terminal output character budget for this poll."
                ),
                "max_output_tokens": _nullable_integer(
                    "Optional Codex-style terminal output token budget alias for this poll."
                ),
            }
        ),
        "cancel_command": _strict_object(
            {
                "command_run_id": _string("Managed command run id to cancel."),
                "reason": _nullable_string("Reason for cancellation."),
            }
        ),
        "read_command_output": _strict_object(
            {
                "command_run_id": _string("Managed command run id to read."),
                "offset": _nullable_integer("Output spool character offset."),
                "max_chars": _nullable_integer("Maximum output characters to return."),
            }
        ),
        "write_file": _strict_object(
            {
                "path": _string("Workspace-relative path to write."),
                "content": _nullable_string("Full file content as a single string."),
                "content_lines": _nullable_string_array(
                    "Full file content as one line per array item. Use for small and medium writes; "
                    "avoid large generated source payloads in one provider-native call."
                ),
                "create": _nullable_boolean(
                    "Whether creating a missing file is allowed."
                ),
                "append": _nullable_boolean(
                    "Whether to append instead of replacing the file."
                ),
                "apply": _nullable_boolean(
                    "Whether to apply the write when writes are approved."
                ),
                "dry_run": _nullable_boolean(
                    "Whether to preview the write without applying it."
                ),
            }
        ),
        "edit_file": _strict_object(
            {
                "path": _string("Workspace-relative path to edit."),
                "old_string": _nullable_string("Existing text to replace."),
                "new_string": _nullable_string("Replacement text."),
                "old": _nullable_string("Legacy alias for old_string."),
                "new": _nullable_string("Legacy alias for new_string."),
                "replace_all": _nullable_boolean(
                    "Whether to replace every occurrence."
                ),
                "apply": _nullable_boolean(
                    "Whether to apply the edit when writes are approved."
                ),
                "dry_run": _nullable_boolean(
                    "Whether to preview the edit without applying it."
                ),
            }
        ),
        "finish": _strict_object(
            {
                "summary": _string("Concise completion summary."),
                "evidence_refs": _string_array("Evidence refs supporting completion."),
                "final_status": _nullable_string("Optional final status label."),
            }
        ),
    }
    return schemas.get(tool_name)


def stable_json_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _function_tool(
    spec: ImplementLaneToolSpec,
    schema: dict[str, object],
    *,
    strict: bool,
    strict_false_reason: str,
    validation: StrictSchemaValidationResult,
) -> LoweredNativeToolSpec:
    return LoweredNativeToolSpec(
        name=spec.name,
        provider_tool={
            "type": "function",
            "name": spec.name,
            "description": spec.description,
            "parameters": schema,
            "strict": strict,
        },
        provider_tool_kind="function",
        strict=strict,
        strict_false_reason=strict_false_reason,
        validation=validation,
    )


def _command_schema() -> dict[str, object]:
    return _strict_object(
        {
            "command": _nullable_string(
                "Command string to run through the managed shell."
            ),
            "argv": _nullable_string_array(
                "Command argv array to run without shell parsing."
            ),
            "cwd": _nullable_string("Workspace-relative working directory."),
            "timeout_ms": _nullable_integer("Maximum command runtime in milliseconds."),
            "max_output_chars": _nullable_integer(
                "Optional provider-visible terminal output character budget for this command."
            ),
            "max_output_tokens": _nullable_integer(
                "Optional Codex-style terminal output token budget alias for this command."
            ),
        }
    )


def _apply_patch_json_fallback_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "input": _string("The complete apply_patch payload."),
            "patch": _string("Legacy alias for the complete apply_patch payload."),
            "patch_lines": _string_array("The apply_patch payload split into lines."),
            "dry_run": _nullable_boolean(
                "Whether to preview the patch without applying it."
            ),
        },
        "required": ["input"],
        "additionalProperties": False,
    }


def _validate_strict_node(
    node: Mapping[str, object], *, path: str, errors: list[str]
) -> None:
    node_type = node.get("type")
    node_types = tuple(node_type) if isinstance(node_type, list) else (node_type,)
    if "object" in node_types:
        properties = node.get("properties")
        if not isinstance(properties, Mapping):
            errors.append(f"{path}:object_missing_properties")
            return
        required = node.get("required")
        if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
            errors.append(f"{path}:object_missing_required")
        else:
            property_names = {str(name) for name in properties}
            required_names = {str(name) for name in required}
            missing = sorted(property_names - required_names)
            extra = sorted(required_names - property_names)
            if missing:
                errors.append(f"{path}:required_missing_properties:{','.join(missing)}")
            if extra:
                errors.append(f"{path}:required_unknown_properties:{','.join(extra)}")
        if node.get("additionalProperties") is not False:
            errors.append(f"{path}:additionalProperties_not_false")
        for name, child in properties.items():
            if isinstance(child, Mapping):
                _validate_strict_node(
                    child, path=f"{path}.properties.{name}", errors=errors
                )
    items = node.get("items")
    if isinstance(items, Mapping):
        _validate_strict_node(items, path=f"{path}.items", errors=errors)
    for key in ("anyOf", "oneOf", "allOf"):
        variants = node.get(key)
        if isinstance(variants, Sequence) and not isinstance(variants, (str, bytes)):
            for index, variant in enumerate(variants):
                if isinstance(variant, Mapping):
                    _validate_strict_node(
                        variant, path=f"{path}.{key}[{index}]", errors=errors
                    )


def _strict_object(properties: Mapping[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(properties),
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, object]:
    return {"type": "string", "description": description}


def _nullable_string(description: str) -> dict[str, object]:
    return {"type": ["string", "null"], "description": description}


def _string_array(description: str) -> dict[str, object]:
    return {
        "type": "array",
        "items": {"type": "string"},
        "description": description,
    }


def _nullable_string_array(description: str) -> dict[str, object]:
    return {
        "type": ["array", "null"],
        "items": {"type": "string"},
        "description": description,
    }


def _nullable_integer(description: str) -> dict[str, object]:
    return {"type": ["integer", "null"], "description": description}


def _nullable_boolean(description: str) -> dict[str, object]:
    return {"type": ["boolean", "null"], "description": description}


def _nullable_enum(description: str, values: Sequence[str]) -> dict[str, object]:
    return {
        "type": ["string", "null"],
        "enum": [*values, None],
        "description": description,
    }


__all__ = [
    "APPLY_PATCH_LARK_GRAMMAR",
    "NATIVE_TOOL_SCHEMA_VERSION",
    "LoweredNativeToolSpec",
    "NativeToolSchemaCapabilities",
    "StrictSchemaValidationResult",
    "lower_implement_lane_tool_spec",
    "lower_implement_lane_tool_specs",
    "lowered_tool_descriptor_metadata",
    "provider_tool_spec_hash",
    "provider_tool_specs",
    "stable_json_hash",
    "strict_false_reasons",
    "structured_tool_json_schema",
    "validate_strict_json_schema",
]
