"""Tool surface registry for implement_v2 native tool profiles.

The registry is intentionally mechanical: it selects and records a provider
visible tool surface for an explicit profile, but it does not decide what the
model should do next.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re

from .native_tool_schema import stable_json_hash
from .tool_policy import ImplementLaneToolSpec, list_v2_tool_specs_for_task

MEW_LEGACY_PROFILE_ID = "mew_legacy"
CODEX_HOT_PATH_PROFILE_ID = "codex_hot_path"
DEFAULT_TOOL_SURFACE_PROFILE_ID = MEW_LEGACY_PROFILE_ID
TOOL_REGISTRY_SCHEMA_VERSION = 1

PROCESS_LIFECYCLE_TOOL_NAMES = frozenset(
    {"poll_command", "cancel_command", "read_command_output"}
)
_COMMAND_OUTPUT_REF_RE = re.compile(
    r"(?:^|[\s;,])(?:command_run_id|command_output_ref|spool_path)=['\"]?(?P<id>[^'\"\s;,]+)"
    r"|Process running with session ID (?P<session>[^\s]+)"
)
_IMPLEMENT_V2_EXEC_REF_RE = re.compile(
    r"implement-v2-exec://[^/\s]+/(?P<id>[^/\s]+)/output"
)

ToolVisibility = str


@dataclass(frozen=True)
class ToolSurfaceProfile:
    """Static identity and policy labels for a selectable tool surface."""

    profile_id: str
    profile_version: str
    prompt_contract_id: str
    render_policy_id: str
    default_parallel_tool_calls: bool = True
    interactive_stdin: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "prompt_contract_id": self.prompt_contract_id,
            "render_policy_id": self.render_policy_id,
            "default_parallel_tool_calls": self.default_parallel_tool_calls,
            "interactive_stdin": self.interactive_stdin,
        }


@dataclass(frozen=True)
class ToolRegistryEntry:
    """Provider-visible route from a tool descriptor to an internal kernel."""

    provider_name: str
    internal_kernel: str
    visibility: ToolVisibility
    access: str
    render_policy_id: str
    family: str
    availability_class: str
    descriptor_adapter_id: str
    argument_adapter_id: str
    supports_parallel_tool_calls: bool
    route_hash: str

    def as_dict(self) -> dict[str, object]:
        return {
            "provider_name": self.provider_name,
            "internal_kernel": self.internal_kernel,
            "visibility": self.visibility,
            "access": self.access,
            "render_policy_id": self.render_policy_id,
            "family": self.family,
            "availability_class": self.availability_class,
            "descriptor_adapter_id": self.descriptor_adapter_id,
            "argument_adapter_id": self.argument_adapter_id,
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "route_hash": self.route_hash,
        }


@dataclass(frozen=True)
class ToolSurfaceSnapshot:
    """Auditable tool-surface decision for one provider request."""

    schema_version: int
    profile: ToolSurfaceProfile
    profile_options: Mapping[str, object]
    mode: str
    provider_tool_names: tuple[str, ...]
    tool_specs: tuple[ImplementLaneToolSpec, ...]
    entries: tuple[ToolRegistryEntry, ...]
    profile_hash: str
    descriptor_hash: str
    route_table_hash: str
    render_policy_hash: str
    parallel_tool_calls_requested: bool
    parallel_tool_calls_effective: bool
    interactive_stdin: bool

    @property
    def profile_id(self) -> str:
        return self.profile.profile_id

    @property
    def profile_version(self) -> str:
        return self.profile.profile_version

    @property
    def prompt_contract_id(self) -> str:
        return self.profile.prompt_contract_id

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_hash": self.profile_hash,
            "descriptor_hash": self.descriptor_hash,
            "route_table_hash": self.route_table_hash,
            "render_policy_hash": self.render_policy_hash,
            "prompt_contract_id": self.prompt_contract_id,
            "parallel_tool_calls_requested": self.parallel_tool_calls_requested,
            "parallel_tool_calls_effective": self.parallel_tool_calls_effective,
            "interactive_stdin": self.interactive_stdin,
            "profile_options": dict(self.profile_options),
            "mode": self.mode,
            "provider_tool_names": list(self.provider_tool_names),
            "tool_specs": [spec.as_dict() for spec in self.tool_specs],
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def request_metadata(self) -> dict[str, object]:
        """Return compact descriptor/inventory metadata without tool bodies."""

        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_hash": self.profile_hash,
            "descriptor_hash": self.descriptor_hash,
            "route_table_hash": self.route_table_hash,
            "render_policy_hash": self.render_policy_hash,
            "prompt_contract_id": self.prompt_contract_id,
            "parallel_tool_calls_requested": self.parallel_tool_calls_requested,
            "parallel_tool_calls_effective": self.parallel_tool_calls_effective,
            "interactive_stdin": self.interactive_stdin,
            "profile_options": dict(self.profile_options),
            "provider_tool_names": list(self.provider_tool_names),
            "entries": [entry.as_dict() for entry in self.entries],
        }


def tool_surface_profile_id(lane_config: Mapping[str, object] | None) -> str:
    """Return the explicit tool-surface profile id, defaulting to mew_legacy."""

    config = lane_config or {}
    profile_id = str(
        config.get("tool_surface_profile_id")
        or config.get("tool_profile")
        or DEFAULT_TOOL_SURFACE_PROFILE_ID
    ).strip()
    return profile_id or DEFAULT_TOOL_SURFACE_PROFILE_ID


def tool_surface_profile_options(
    lane_config: Mapping[str, object] | None,
) -> dict[str, object]:
    """Return explicit profile options only."""

    config = lane_config or {}
    raw_options = config.get("tool_surface_profile_options")
    if isinstance(raw_options, Mapping):
        return dict(raw_options)
    return {}


def build_tool_surface_snapshot(
    *,
    lane_config: Mapping[str, object] | None,
    task_contract: object = None,
    transcript_items: object = None,
    available_provider_tool_names: Sequence[str] | None = None,
    provider_supports_parallel_tool_calls: bool = True,
) -> ToolSurfaceSnapshot:
    """Build a deterministic tool-surface snapshot for one provider request."""

    profile_id = tool_surface_profile_id(lane_config)
    mode = str((lane_config or {}).get("mode") or "full")
    profile_options = tool_surface_profile_options(lane_config)
    if profile_id == CODEX_HOT_PATH_PROFILE_ID:
        return _codex_hot_path_snapshot(
            mode=mode,
            profile_options=profile_options,
            available_provider_tool_names=available_provider_tool_names,
            provider_supports_parallel_tool_calls=provider_supports_parallel_tool_calls,
        )
    if profile_id != MEW_LEGACY_PROFILE_ID:
        raise ValueError(f"unsupported tool_surface_profile_id: {profile_id}")

    profile = ToolSurfaceProfile(
        profile_id=MEW_LEGACY_PROFILE_ID,
        profile_version="v1",
        prompt_contract_id="mew_legacy_prompt_v1",
        render_policy_id="mew_legacy_result_cards_v1",
        default_parallel_tool_calls=True,
        interactive_stdin=False,
    )
    specs = list_v2_tool_specs_for_task(mode, task_contract=task_contract)
    specs = _filter_mew_legacy_lifecycle_tools(specs, transcript_items)
    if available_provider_tool_names is not None:
        names = {str(name) for name in available_provider_tool_names}
        specs = tuple(spec for spec in specs if spec.name in names)

    entries = tuple(_mew_legacy_entry(spec, profile) for spec in specs)
    descriptor_payload = [spec.as_dict() for spec in specs]
    route_payload = [entry.as_dict() for entry in entries]
    profile_payload = profile.as_dict()
    render_payload = {
        "profile_id": profile.profile_id,
        "render_policy_id": profile.render_policy_id,
        "provider_tool_names": [spec.name for spec in specs],
    }
    requested_parallel = profile.default_parallel_tool_calls
    effective_parallel = requested_parallel and bool(provider_supports_parallel_tool_calls)
    return ToolSurfaceSnapshot(
        schema_version=TOOL_REGISTRY_SCHEMA_VERSION,
        profile=profile,
        profile_options=profile_options,
        mode=mode,
        provider_tool_names=tuple(spec.name for spec in specs),
        tool_specs=tuple(specs),
        entries=entries,
        profile_hash=stable_json_hash(profile_payload),
        descriptor_hash=stable_json_hash(descriptor_payload),
        route_table_hash=stable_json_hash(route_payload),
        render_policy_hash=stable_json_hash(render_payload),
        parallel_tool_calls_requested=requested_parallel,
        parallel_tool_calls_effective=effective_parallel,
        interactive_stdin=profile.interactive_stdin,
    )


def _codex_hot_path_snapshot(
    *,
    mode: str,
    profile_options: Mapping[str, object],
    available_provider_tool_names: Sequence[str] | None,
    provider_supports_parallel_tool_calls: bool,
) -> ToolSurfaceSnapshot:
    profile = ToolSurfaceProfile(
        profile_id=CODEX_HOT_PATH_PROFILE_ID,
        profile_version="v0",
        prompt_contract_id="codex_hot_path_prompt_v1",
        render_policy_id="codex_hot_path_result_text_v1",
        default_parallel_tool_calls=True,
        interactive_stdin=False,
    )
    effective_options = {"write_stdin_mode": "poll_only", **dict(profile_options)}
    specs = _codex_hot_path_specs(enable_list_dir=effective_options.get("enable_list_dir") is True)
    if available_provider_tool_names is not None:
        names = {str(name) for name in available_provider_tool_names}
        specs = tuple(spec for spec in specs if spec.name in names)
    entries = tuple(_codex_hot_path_entry(spec, profile) for spec in specs)
    descriptor_payload = [spec.as_dict() for spec in specs]
    route_payload = [entry.as_dict() for entry in entries]
    render_payload = {
        "profile_id": profile.profile_id,
        "render_policy_id": profile.render_policy_id,
        "provider_tool_names": [spec.name for spec in specs],
    }
    requested_parallel = profile.default_parallel_tool_calls
    effective_parallel = requested_parallel and bool(provider_supports_parallel_tool_calls)
    return ToolSurfaceSnapshot(
        schema_version=TOOL_REGISTRY_SCHEMA_VERSION,
        profile=profile,
        profile_options=effective_options,
        mode=mode,
        provider_tool_names=tuple(spec.name for spec in specs),
        tool_specs=tuple(specs),
        entries=entries,
        profile_hash=stable_json_hash(profile.as_dict()),
        descriptor_hash=stable_json_hash(descriptor_payload),
        route_table_hash=stable_json_hash(route_payload),
        render_policy_hash=stable_json_hash(render_payload),
        parallel_tool_calls_requested=requested_parallel,
        parallel_tool_calls_effective=effective_parallel,
        interactive_stdin=profile.interactive_stdin,
    )


def _codex_hot_path_specs(*, enable_list_dir: bool) -> tuple[ImplementLaneToolSpec, ...]:
    legacy_by_name = {spec.name: spec for spec in list_v2_tool_specs_for_task("full")}
    specs = [
        legacy_by_name["apply_patch"],
        ImplementLaneToolSpec(
            name="exec_command",
            access="execute",
            description=(
                "Run a bounded shell command in the workspace. Use it for builds, "
                "tests, and probes; use apply_patch for source edits."
            ),
            approval_required=True,
        ),
        ImplementLaneToolSpec(
            name="write_stdin",
            access="execute",
            description=(
                "Poll an existing yielded command session with empty chars. "
                "Interactive stdin is disabled in this profile version."
            ),
        ),
        legacy_by_name["finish"],
    ]
    if enable_list_dir:
        specs.insert(
            1,
            ImplementLaneToolSpec(
                name="list_dir",
                access="read",
                description="List a workspace directory with bounded entries.",
            ),
        )
    return tuple(specs)


def _codex_hot_path_entry(
    spec: ImplementLaneToolSpec,
    profile: ToolSurfaceProfile,
) -> ToolRegistryEntry:
    internal_kernel = {
        "exec_command": "run_command",
        "write_stdin": "poll_command",
        "list_dir": "inspect_dir",
    }.get(spec.name, spec.name)
    family = _tool_family(spec)
    availability_class = _availability_class(spec, family=family)
    if spec.name == "write_stdin":
        family = "lifecycle"
        availability_class = "active_session"
    payload = {
        "provider_name": spec.name,
        "internal_kernel": internal_kernel,
        "visibility": "provider_visible",
        "access": spec.access,
        "render_policy_id": profile.render_policy_id,
        "family": family,
        "availability_class": availability_class,
        "descriptor_adapter_id": "codex_hot_path_descriptor_v1",
        "argument_adapter_id": f"codex_hot_path_{spec.name}_arguments_v1",
        "supports_parallel_tool_calls": True,
    }
    return ToolRegistryEntry(
        provider_name=spec.name,
        internal_kernel=internal_kernel,
        visibility="provider_visible",
        access=spec.access,
        render_policy_id=profile.render_policy_id,
        family=family,
        availability_class=availability_class,
        descriptor_adapter_id="codex_hot_path_descriptor_v1",
        argument_adapter_id=f"codex_hot_path_{spec.name}_arguments_v1",
        supports_parallel_tool_calls=True,
        route_hash=stable_json_hash(payload),
    )


def _mew_legacy_entry(
    spec: ImplementLaneToolSpec,
    profile: ToolSurfaceProfile,
) -> ToolRegistryEntry:
    family = _tool_family(spec)
    availability_class = _availability_class(spec, family=family)
    payload = {
        "provider_name": spec.name,
        "internal_kernel": spec.name,
        "visibility": "provider_visible",
        "access": spec.access,
        "render_policy_id": profile.render_policy_id,
        "family": family,
        "availability_class": availability_class,
        "descriptor_adapter_id": "mew_legacy_descriptor_v1",
        "argument_adapter_id": "mew_legacy_arguments_identity_v1",
        "supports_parallel_tool_calls": True,
    }
    return ToolRegistryEntry(
        provider_name=spec.name,
        internal_kernel=spec.name,
        visibility="provider_visible",
        access=spec.access,
        render_policy_id=profile.render_policy_id,
        family=family,
        availability_class=availability_class,
        descriptor_adapter_id="mew_legacy_descriptor_v1",
        argument_adapter_id="mew_legacy_arguments_identity_v1",
        supports_parallel_tool_calls=True,
        route_hash=stable_json_hash(payload),
    )


def _tool_family(spec: ImplementLaneToolSpec) -> str:
    if spec.name in PROCESS_LIFECYCLE_TOOL_NAMES:
        return "lifecycle"
    if spec.access == "finish":
        return "finish"
    return spec.access


def _availability_class(spec: ImplementLaneToolSpec, *, family: str) -> str:
    if family == "lifecycle":
        return "active_session"
    if spec.access == "finish":
        return "always"
    return "permission_mode"


def _filter_mew_legacy_lifecycle_tools(
    specs: tuple[ImplementLaneToolSpec, ...],
    transcript_items: object,
) -> tuple[ImplementLaneToolSpec, ...]:
    if _has_open_command(transcript_items):
        return specs
    if _has_completed_command_output(transcript_items):
        return tuple(
            spec for spec in specs if spec.name not in {"poll_command", "cancel_command"}
        )
    return tuple(spec for spec in specs if spec.name not in PROCESS_LIFECYCLE_TOOL_NAMES)


def _has_open_command(transcript_items: object) -> bool:
    return any(
        bool(state.get("is_open"))
        for state in _latest_command_lifecycle_states(transcript_items).values()
    )


def _has_completed_command_output(transcript_items: object) -> bool:
    return any(
        (not bool(state.get("is_open"))) and bool(state.get("has_output_ref"))
        for state in _latest_command_lifecycle_states(transcript_items).values()
    )


def _latest_command_lifecycle_states(transcript_items: object) -> dict[str, dict[str, object]]:
    if not isinstance(transcript_items, Sequence) or isinstance(
        transcript_items, (str, bytes, bytearray)
    ):
        return {}
    states: dict[str, dict[str, object]] = {}
    for raw_item in transcript_items:
        item = _item_mapping(raw_item)
        if str(item.get("kind") or "") not in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            continue
        call_id = str(item.get("call_id") or "").strip()
        tool_name = str(item.get("tool_name") or "").strip()
        if not call_id or tool_name not in {
            "exec_command",
            "write_stdin",
            "run_command",
            "run_tests",
            "poll_command",
            "cancel_command",
        }:
            continue
        command_run_id = _command_run_id_from_item(item)
        if not command_run_id:
            continue
        previous = states.get(command_run_id)
        sequence = _safe_int(item.get("sequence"), default=0)
        if previous and int(previous.get("sequence") or -1) > sequence:
            continue
        status = str(item.get("status") or "").strip().casefold()
        text = str(item.get("output_text_or_ref") or "")
        has_content_ref = bool(
            item.get("content_refs")
            if isinstance(item.get("content_refs"), Sequence)
            and not isinstance(item.get("content_refs"), (str, bytes, bytearray))
            else False
        )
        states[command_run_id] = {
            "sequence": sequence,
            "status": status,
            "is_open": status in {"yielded", "running", "pending"},
            "has_output_ref": "command_output_ref=" in text
            or "command_run_id=" in text
            or "spool_path=" in text
            or "Process running with session ID " in text
            or has_content_ref,
        }
    return states


def _item_mapping(item: object) -> Mapping[str, object]:
    if isinstance(item, Mapping):
        return item
    if hasattr(item, "as_dict"):
        value = item.as_dict()
        if isinstance(value, Mapping):
            return value
    return {}


def _command_run_id_from_item(item: Mapping[str, object]) -> str:
    text = str(item.get("output_text_or_ref") or "")
    match = _COMMAND_OUTPUT_REF_RE.search(text)
    if match:
        return str(match.group("id") or match.group("session") or "")
    refs = item.get("content_refs")
    if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes, bytearray)):
        for ref in refs:
            ref_text = str(ref or "")
            match = _COMMAND_OUTPUT_REF_RE.search(ref_text)
            if match:
                return match.group("id")
            match = _IMPLEMENT_V2_EXEC_REF_RE.search(ref_text)
            if match:
                return match.group("id")
    return ""


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


__all__ = [
    "CODEX_HOT_PATH_PROFILE_ID",
    "DEFAULT_TOOL_SURFACE_PROFILE_ID",
    "MEW_LEGACY_PROFILE_ID",
    "PROCESS_LIFECYCLE_TOOL_NAMES",
    "TOOL_REGISTRY_SCHEMA_VERSION",
    "ToolRegistryEntry",
    "ToolSurfaceProfile",
    "ToolSurfaceSnapshot",
    "build_tool_surface_snapshot",
    "tool_surface_profile_id",
    "tool_surface_profile_options",
]
