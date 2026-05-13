"""Shared local tool execution kernel.

The kernel is the common execution boundary for human-facing ``mew tool`` and
model-facing implement_v2 tool calls. Lanes may still decide which tools are
visible, which approvals are valid, and how results are projected, but the
actual read/write/exec behavior should live here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from .implement_lane.types import ToolCallEnvelope, ToolResultEnvelope
    from .implement_lane.write_runtime import ImplementV2WriteRuntime

@dataclass(frozen=True)
class ToolKernelConfig:
    """Policy inputs shared by CLI and implement_v2 tool execution."""

    workspace: object = "."
    mode: str = "full"
    allowed_read_roots: tuple[str, ...] = ()
    allowed_write_roots: tuple[str, ...] = ()
    approved_write_calls: tuple[object, ...] = ()
    allow_shell: bool = False
    allow_verify: bool = False
    allow_governance_writes: bool = False
    run_command_available: bool = True
    route_run_tests_shell_surface: bool = True
    source_write_tools_available: bool | None = None
    task_contract: dict[str, object] = field(default_factory=dict)
    frontier_state: dict[str, object] = field(default_factory=dict)
    source_mutation_roots: tuple[str, ...] = ()
    max_active: int = 1
    read_result_max_chars: int | None = None
    surface_label: str = "tool"


class ToolKernel:
    """Execute provider-neutral mew tools through shared read/write/exec substrates."""

    def __init__(
        self,
        config: ToolKernelConfig,
        *,
        exec_runtime: ImplementV2ManagedExecRuntime | None = None,
        write_runtime: ImplementV2WriteRuntime | None = None,
    ):
        from .implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
        from .implement_lane.write_runtime import ImplementV2WriteRuntime

        self.config = config
        workspace = _resolved_workspace(config.workspace)
        self.allowed_read_roots = _effective_roots(
            config.allowed_read_roots,
            workspace=workspace,
            default=(str(workspace),),
        )
        self.allowed_write_roots = _effective_roots(
            config.allowed_write_roots,
            workspace=workspace,
            default=(),
        )
        self.source_mutation_roots = _effective_roots(
            config.source_mutation_roots,
            workspace=workspace,
            default=(str(workspace),),
        )
        self.exec_runtime = exec_runtime or ImplementV2ManagedExecRuntime(
            workspace=str(workspace),
            allowed_roots=self.allowed_read_roots,
            max_active=config.max_active,
            allow_shell=config.allow_shell,
            run_command_available=config.run_command_available,
            route_run_tests_shell_surface=config.route_run_tests_shell_surface,
            source_write_tools_available=self._source_write_tools_available(),
            task_contract=config.task_contract,
            frontier_state=config.frontier_state,
            source_mutation_roots=self.source_mutation_roots,
        )
        self.write_runtime = write_runtime or ImplementV2WriteRuntime(
            workspace=str(workspace),
            allowed_write_roots=self.allowed_write_roots,
            approved_write_calls=config.approved_write_calls,
            allow_governance_writes=config.allow_governance_writes,
        )

    def execute(self, call: ToolCallEnvelope) -> ToolResultEnvelope:
        """Execute one tool call under the configured policy."""

        from .implement_lane.tool_routes import with_tool_route_decision

        if not self._available(call.tool_name):
            return with_tool_route_decision(
                call,
                _build_invalid_tool_result(
                    call,
                    reason=f"{call.tool_name} is not available in {self.config.surface_label} {self.config.mode} mode",
                ),
            )
        if call.tool_name in _write_tool_names():
            if not self.allowed_write_roots:
                return with_tool_route_decision(
                    call,
                    _build_invalid_tool_result(call, reason="write tools are disabled; pass --allow-write PATH"),
                )
            return with_tool_route_decision(call, self.write_runtime.execute(call))
        if call.tool_name in _exec_tool_names():
            if call.tool_name == "run_tests" and not self.config.allow_verify:
                return with_tool_route_decision(
                    call,
                    _build_invalid_tool_result(call, reason="run_tests is disabled; pass --allow-verify"),
                )
            if call.tool_name == "run_command" and not self.config.allow_shell:
                return with_tool_route_decision(
                    call,
                    _build_invalid_tool_result(call, reason="run_command is disabled; pass --allow-shell"),
                )
            return with_tool_route_decision(call, self.exec_runtime.execute(call))
        from .implement_lane.read_runtime import execute_read_only_tool_call

        return with_tool_route_decision(
            call,
            execute_read_only_tool_call(
                call,
                workspace=self.config.workspace,
                allowed_roots=self.allowed_read_roots,
                result_max_chars=self.config.read_result_max_chars
                if self.config.read_result_max_chars is not None
                else 12_000,
            ),
        )

    def cancel_active_commands(self, *, reason: str) -> tuple[dict[str, object], ...]:
        return self.exec_runtime.cancel_active_commands(reason=reason)

    def finalize_active_commands(self, *, timeout_seconds: float | None = None) -> tuple[dict[str, object], ...]:
        return self.exec_runtime.finalize_active_commands(timeout_seconds=timeout_seconds)

    def poll_active_commands(self, *, wait_seconds: float | None = None) -> tuple[dict[str, object], ...]:
        return self.exec_runtime.poll_active_commands(wait_seconds=wait_seconds)

    def _available(self, tool_name: object) -> bool:
        from .implement_lane.tool_policy import list_v2_tool_specs_for_task

        return str(tool_name or "") in {
            spec.name
            for spec in list_v2_tool_specs_for_task(
                self.config.mode,
                task_contract=self.config.task_contract,
            )
        }

    def _source_write_tools_available(self) -> bool:
        if self.config.source_write_tools_available is not None:
            return bool(self.config.source_write_tools_available)
        return bool(self.allowed_write_roots) and any(
            self._available(tool_name) for tool_name in ("write_file", "edit_file", "apply_patch")
        )


def make_tool_call_envelope(
    tool_name: str,
    arguments: dict[str, object],
    *,
    lane_attempt_id: str = "mew-tool-cli",
    provider_call_id: str = "call-cli",
    mew_tool_call_id: str = "tool-cli",
    turn_index: int = 1,
) -> ToolCallEnvelope:
    from .implement_lane.types import ToolCallEnvelope

    return ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="mew-cli",
        provider_call_id=provider_call_id,
        mew_tool_call_id=mew_tool_call_id,
        tool_name=tool_name,
        arguments=dict(arguments),
        turn_index=turn_index,
    )


def _resolved_workspace(workspace: object) -> Path:
    return Path(str(workspace or ".")).expanduser().resolve(strict=False)


def _effective_roots(
    roots: tuple[str, ...],
    *,
    workspace: Path,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    raw_roots = tuple(str(root) for root in roots if str(root or "").strip()) or default
    resolved: list[str] = []
    for raw in raw_roots:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = workspace / candidate
        value = str(candidate.resolve(strict=False))
        if value not in resolved:
            resolved.append(value)
    return tuple(resolved)


def _build_invalid_tool_result(call: ToolCallEnvelope, *, reason: str) -> ToolResultEnvelope:
    from .implement_lane.replay import build_invalid_tool_result

    return build_invalid_tool_result(call, reason=reason)


def _exec_tool_names() -> frozenset[str]:
    from .implement_lane.exec_runtime import EXEC_TOOL_NAMES

    return EXEC_TOOL_NAMES


def _write_tool_names() -> frozenset[str]:
    from .implement_lane.write_runtime import WRITE_TOOL_NAMES

    return WRITE_TOOL_NAMES


__all__ = [
    "ToolKernel",
    "ToolKernelConfig",
    "make_tool_call_envelope",
]
