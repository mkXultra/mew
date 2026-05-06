"""Prompt section assembly for the default-off implement_v2 lane."""

from __future__ import annotations

import json

from ..prompt_sections import (
    CACHE_POLICY_CACHEABLE,
    CACHE_POLICY_DYNAMIC,
    CACHE_POLICY_SESSION,
    STABILITY_DYNAMIC,
    STABILITY_SEMI_STATIC,
    STABILITY_STATIC,
    PromptSection,
    prompt_section_metrics,
)
from .tool_policy import ImplementLaneToolSpec, list_v2_tool_specs_for_mode
from .types import ImplementLaneInput


def build_implement_v2_prompt_sections(
    lane_input: ImplementLaneInput,
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...] | None = None,
) -> list[PromptSection]:
    """Build provider-neutral v2 prompt sections without provider cache transport."""

    mode = str(lane_input.lane_config.get("mode") or "read_only")
    specs = tool_specs if tool_specs is not None else list_v2_tool_specs_for_mode(mode)
    sections = [
        PromptSection(
            id="implement_v2_lane_base",
            version="v0",
            title="Implement V2 Lane Base",
            content=(
                "You are running inside the default-off implement_v2 lane. "
                "Use provider-shaped tool calls through the selected v2 transport, "
                "preserve paired tool results, "
                "and finish only through deterministic mew acceptance evidence."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
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
        ),
        PromptSection(
            id="implement_v2_execution_artifact_contract",
            version="v0",
            title="Implement V2 Execution Artifact Contract",
            content=(
                "For run_command and run_tests, attach an execution_contract when the command is intended to build, "
                "run, verify, or prove an artifact. poll_command inherits the original command's contract by "
                "command_run_id; do not introduce new artifact obligations only on a later poll. Declare role, "
                "stage, purpose, proof_role, "
                "acceptance_kind, expected_exit, and expected_artifacts. Expected artifacts should name path or "
                "stream targets plus cheap checks such as exists, non_empty, kind, size_between, text_contains, "
                "or regex. Mew owns artifact checking at runtime; do not treat stdout/stderr text markers as proof "
                "when an artifact contract exists. A finish claim should cite structured evidence ids, artifact "
                "evidence ids, verifier evidence, or blocker classes from the latest tool result instead of only "
                "describing terminal output. If task or frontier state already declares a final artifact, a "
                "verifier-shaped command may rely on mew to runtime-infer that artifact, but explicit "
                "expected_artifacts are preferred."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_tool_surface",
            version="v0",
            title="Implement V2 Tool Surface",
            content=_tool_surface_json(specs),
            stability=STABILITY_SEMI_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_compatibility_frontier",
            version="v0",
            title="Implement V2 Compatibility Frontier",
            content=(
                "When a runtime/build failure points to dependency, language-version, or ABI compatibility, "
                "broaden the edit frontier before finishing. Search sibling source surfaces that can carry the "
                "same compatibility bug instead of patching only the first traceback file. For Python native, "
                "compiled, or Cython extension tasks, include Python and compiled-source surfaces such as "
                "`*.py`, `*.pyx`, `*.pxd`, `setup.py`, `pyproject.toml`, extension modules, and focused tests. "
                "An import-only smoke proves loadability, not behavior; run a small behavior smoke or focused "
                "test that exercises the repaired extension path before claiming completion."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
    ]
    hard_runtime_profile_active = is_hard_runtime_artifact_task(lane_input.task_contract)
    hard_runtime_frontier = _hard_runtime_frontier_state(lane_input.persisted_lane_state)
    if hard_runtime_profile_active:
        sections.append(
            PromptSection(
                id="implement_v2_hard_runtime_profile",
                version="v0",
                title="Implement V2 Hard Runtime Profile",
                content=(
                    "For tasks involving provided source plus a VM, emulator, interpreter, ELF/binary, "
                    "or runtime-generated artifact, preserve the source-provided implementation path. "
                    "Do not replace the requested program with a handcrafted stub, surrogate binary, "
                    "or synthetic artifact producer unless the task explicitly asks for a shim. Treat "
                    "minimal stand-ins as diagnostic probes only. Inspect the provided source/build files, "
                    "build or repair that source, and keep verifier evidence tied to the final deliverable. "
                    "For runtime visual, frame, screenshot, log, socket, or pid artifacts, final proof must "
                    "come from a fresh verifier-shaped run in the final cwd and must ground the required "
                    "stdout/boot markers plus artifact quality such as expected dimensions, reference "
                    "similarity, semantic content, or exact output markers. If the final verifier is expected "
                    "to create the artifact, remove stale self-check artifacts before finish. When a binary "
                    "or runtime-generated artifact fails inside a VM, emulator, interpreter, or loader, compare "
                    "the artifact ABI/ISA/endianness/entrypoint with the runtime loader contract before another "
                    "broad rebuild or finish. If those conditions are not proven, continue or report a precise "
                    "runtime gap; do not complete."
                ),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="implement_v2",
            )
        )
    if hard_runtime_profile_active or hard_runtime_frontier:
        sections.append(
            PromptSection(
                id="implement_v2_hard_runtime_frontier_state",
                version="v0",
                title="Implement V2 Hard Runtime Frontier State",
                content=_stable_json(
                    {
                        "instructions": (
                            "Use this compact state before broad rediscovery. Update it when a newer "
                            "build/runtime result supersedes it. Do not finish from this state alone; "
                            "completion still requires deterministic terminal/write evidence."
                        ),
                        "lane_hard_runtime_frontier": hard_runtime_frontier
                        or {"schema_version": 1, "status": "active", "source": "not_yet_populated"},
                    }
                ),
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement_v2",
            )
        )
    sections.extend(
        [
            PromptSection(
                id="implement_v2_task_contract",
                version="v0",
                title="Implement V2 Task Contract",
                content=_stable_json(lane_input.task_contract),
                stability=STABILITY_SEMI_STATIC,
                cache_policy=CACHE_POLICY_SESSION,
                profile="implement_v2",
            ),
            PromptSection(
                id="implement_v2_lane_state",
                version="v0",
                title="Implement V2 Lane State",
                content=_stable_json(
                    {
                        "work_session_id": lane_input.work_session_id,
                        "task_id": lane_input.task_id,
                        "lane": lane_input.lane,
                        "model_backend": lane_input.model_backend,
                        "model": lane_input.model,
                        "effort": lane_input.effort,
                        "lane_config": lane_input.lane_config,
                        "lane_local_state": _lane_local_state(lane_input.persisted_lane_state),
                    }
                ),
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement_v2",
            ),
        ]
    )
    return sections


def implement_v2_prompt_section_metrics(lane_input: ImplementLaneInput) -> dict[str, object]:
    """Return prompt-section metrics for v2 prompt assembly."""

    return prompt_section_metrics(build_implement_v2_prompt_sections(lane_input))


def _tool_surface_json(tool_specs: tuple[ImplementLaneToolSpec, ...]) -> str:
    return _stable_json({"tools": [spec.as_dict() for spec in tool_specs]})


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2)


def is_hard_runtime_artifact_task(task_contract: object) -> bool:
    text = _contract_text(task_contract)
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


def _contract_text(task_contract: object) -> str:
    if task_contract is None:
        return ""
    if isinstance(task_contract, str):
        return task_contract.lower()
    try:
        return json.dumps(task_contract, ensure_ascii=True, sort_keys=True).lower()
    except TypeError:
        return str(task_contract).lower()


def _lane_local_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    allowed_prefixes = ("lane_", "reentry_", "resume_")
    blocked_terms = ("memory", "typed", "durable", "repair_memory")
    filtered = {}
    for key, value in persisted_lane_state.items():
        key_text = str(key)
        normalized = key_text.lower()
        if not key_text.startswith(allowed_prefixes):
            continue
        if any(term in normalized for term in blocked_terms):
            continue
        filtered[key_text] = value
    return filtered


def _hard_runtime_frontier_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    value = persisted_lane_state.get("lane_hard_runtime_frontier")
    return dict(value) if isinstance(value, dict) else {}


__all__ = [
    "build_implement_v2_prompt_sections",
    "implement_v2_prompt_section_metrics",
    "is_hard_runtime_artifact_task",
]
