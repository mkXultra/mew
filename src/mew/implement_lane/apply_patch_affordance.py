"""Synthetic apply_patch affordance check for implement_v2 hot-path debugging.

The check asks one provider-native turn to choose a tool for a trivial source
mutation under the codex_hot_path surface.  It does not execute the returned
tool call.  The purpose is to separate "the model will not choose apply_patch"
from broader Harbor task-shape failures.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Callable, Mapping

from ..config import DEFAULT_CODEX_REASONING_EFFORT
from ..codex_api import load_codex_oauth
from .native_provider_adapter import (
    NativeProviderCapabilities,
    NativeResponsesStreamParseResult,
    build_responses_request_descriptor,
    call_codex_native_responses,
    call_codex_native_responses_websocket,
)
from .native_tool_schema import stable_json_hash
from .tool_registry import CODEX_HOT_PATH_PROFILE_ID, build_tool_surface_snapshot

APPLY_PATCH_AFFORDANCE_SCHEMA_VERSION = 1
DEFAULT_APPLY_PATCH_AFFORDANCE_MODEL = "gpt-5.5"
DEFAULT_APPLY_PATCH_AFFORDANCE_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_APPLY_PATCH_AFFORDANCE_LANE_ATTEMPT_ID = "m6-24-h6-apply-patch-affordance"


@dataclass(frozen=True)
class ApplyPatchAffordanceScenario:
    """One synthetic source-mutation prompt for apply_patch affordance checks."""

    scenario_id: str
    instructions: str
    user_text: str
    expected_tool: str = "apply_patch"

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "instructions": self.instructions,
            "user_text": self.user_text,
            "expected_tool": self.expected_tool,
        }


@dataclass(frozen=True)
class ApplyPatchAffordanceResult:
    """Auditable result for one apply_patch affordance check."""

    schema_version: int
    status: str
    scenario: ApplyPatchAffordanceScenario
    first_tool_name: str
    first_tool_kind: str
    transcript_item_count: int
    descriptor: Mapping[str, object]
    response: Mapping[str, object]
    elapsed_seconds: float

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "scenario": self.scenario.as_dict(),
            "first_tool_name": self.first_tool_name,
            "first_tool_kind": self.first_tool_kind,
            "transcript_item_count": self.transcript_item_count,
            "descriptor": dict(self.descriptor),
            "response": dict(self.response),
            "elapsed_seconds": self.elapsed_seconds,
        }


def default_apply_patch_affordance_scenario() -> ApplyPatchAffordanceScenario:
    """Return the default H6 synthetic source mutation scenario."""

    return ApplyPatchAffordanceScenario(
        scenario_id="known_path_new_source_file_v1",
        instructions=(
            "You are a coding agent in a repository. Make source changes with the "
            "available source-editing tool. Use shell commands only for running "
            "or inspecting commands; do not use shell redirection or heredocs to "
            "write source files."
        ),
        user_text=(
            "Create `src/affordance_probe.py` with exactly this content:\n\n"
            "def meaning():\n"
            "    return 42\n\n"
            "The target path and exact content are already known. Do not inspect "
            "the repository first. Make the source change now."
        ),
    )


def build_apply_patch_affordance_descriptor(
    scenario: ApplyPatchAffordanceScenario | None = None,
    *,
    model: str = DEFAULT_APPLY_PATCH_AFFORDANCE_MODEL,
    reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT,
) -> dict[str, object]:
    """Build the one-turn provider-native request descriptor for the check."""

    scenario = scenario or default_apply_patch_affordance_scenario()
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full", "tool_surface_profile_id": CODEX_HOT_PATH_PROFILE_ID},
        task_contract=scenario.as_dict(),
        transcript_items=(),
    )
    return build_responses_request_descriptor(
        model=model,
        instructions=scenario.instructions,
        input_items=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": scenario.user_text}],
            }
        ],
        transcript_window=[
            {
                "sequence": 1,
                "kind": "input_message",
                "scenario_id": scenario.scenario_id,
            }
        ],
        tool_specs=snapshot.tool_specs,
        capabilities=NativeProviderCapabilities(),
        reasoning={"effort": reasoning_effort} if reasoning_effort else None,
        provider_request_id=f"affordance-{stable_json_hash(scenario.as_dict()).removeprefix('sha256:')[:16]}",
        tool_surface_snapshot=snapshot.request_metadata(),
    )


def run_apply_patch_affordance_check(
    *,
    scenario: ApplyPatchAffordanceScenario | None = None,
    auth_path: object | None = None,
    model: str = DEFAULT_APPLY_PATCH_AFFORDANCE_MODEL,
    base_url: str = DEFAULT_APPLY_PATCH_AFFORDANCE_BASE_URL,
    timeout: float = 60.0,
    lane_attempt_id: str = DEFAULT_APPLY_PATCH_AFFORDANCE_LANE_ATTEMPT_ID,
    use_websocket: bool = True,
    call_provider: Callable[..., NativeResponsesStreamParseResult] | None = None,
) -> ApplyPatchAffordanceResult:
    """Run one live provider-native affordance check without executing tools."""

    scenario = scenario or default_apply_patch_affordance_scenario()
    descriptor = build_apply_patch_affordance_descriptor(scenario, model=model)
    started = time.monotonic()
    if call_provider is None:
        auth = load_codex_oauth(auth_path)
        if use_websocket:
            response = call_codex_native_responses_websocket(
                auth=auth,
                descriptor=descriptor,
                base_url=base_url,
                timeout=timeout,
                lane_attempt_id=lane_attempt_id,
                turn_id="turn-1",
            )
        else:
            response = call_codex_native_responses(
                auth=auth,
                descriptor=descriptor,
                base_url=base_url,
                timeout=timeout,
                lane_attempt_id=lane_attempt_id,
                turn_id="turn-1",
            )
    else:
        response = call_provider(
            descriptor=descriptor,
            base_url=base_url,
            timeout=timeout,
            lane_attempt_id=lane_attempt_id,
            turn_id="turn-1",
        )
    elapsed = time.monotonic() - started
    first_tool = _first_tool_call(response)
    first_tool_name = str(first_tool.get("tool_name") or "")
    first_tool_kind = str(first_tool.get("kind") or "")
    status = "pass" if first_tool_name == scenario.expected_tool else "fail"
    return ApplyPatchAffordanceResult(
        schema_version=APPLY_PATCH_AFFORDANCE_SCHEMA_VERSION,
        status=status,
        scenario=scenario,
        first_tool_name=first_tool_name,
        first_tool_kind=first_tool_kind,
        transcript_item_count=len(response.transcript.items),
        descriptor=_redact_descriptor(descriptor),
        response=response.as_dict(),
        elapsed_seconds=round(elapsed, 3),
    )


def write_apply_patch_affordance_result(
    result: ApplyPatchAffordanceResult,
    path: object,
) -> Path:
    """Persist an affordance result artifact."""

    output_path = Path(str(path)).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _first_tool_call(response: NativeResponsesStreamParseResult) -> dict[str, object]:
    for item in response.transcript.items:
        if item.kind in {"function_call", "custom_tool_call", "finish_call"}:
            return item.as_dict()
    return {}


def _redact_descriptor(descriptor: Mapping[str, object]) -> dict[str, object]:
    """Keep descriptor artifacts useful without carrying large tool grammar text."""

    data = json.loads(json.dumps(dict(descriptor), ensure_ascii=False))
    request_body = data.get("request_body")
    if isinstance(request_body, dict):
        tools = request_body.get("tools")
        if isinstance(tools, list):
            request_body["tools"] = [_compact_tool_descriptor(tool) for tool in tools if isinstance(tool, dict)]
    return data


def _compact_tool_descriptor(tool: Mapping[str, object]) -> dict[str, object]:
    compact = {key: value for key, value in tool.items() if key not in {"format", "parameters"}}
    if "parameters" in tool:
        compact["parameters_hash"] = stable_json_hash(tool.get("parameters"))
    if "format" in tool:
        compact["format_hash"] = stable_json_hash(tool.get("format"))
    return compact


__all__ = [
    "APPLY_PATCH_AFFORDANCE_SCHEMA_VERSION",
    "ApplyPatchAffordanceResult",
    "ApplyPatchAffordanceScenario",
    "build_apply_patch_affordance_descriptor",
    "default_apply_patch_affordance_scenario",
    "run_apply_patch_affordance_check",
    "write_apply_patch_affordance_result",
]
