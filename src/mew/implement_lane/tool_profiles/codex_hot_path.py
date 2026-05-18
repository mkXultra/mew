"""Codex-like provider-visible tool surface."""

from __future__ import annotations

from dataclasses import dataclass

from ...prompt_sections import (
    CACHE_POLICY_CACHEABLE,
    CACHE_POLICY_SESSION,
    STABILITY_SEMI_STATIC,
    STABILITY_STATIC,
    PromptSection,
)
from ..tool_specs import ImplementLaneToolSpec

CODEX_HOT_PATH_PROFILE_ID = "codex_hot_path"
CODEX_HOT_PATH_PROMPT_CONTRACT_ID = "codex_hot_path_prompt_v1"
CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID = "codex_hot_path_developer_contract_v1"
CODEX_HOT_PATH_DEVELOPER_CONTRACT_VERSION = "v1"


@dataclass(frozen=True)
class DeveloperToolBehaviorContract:
    """Profile-owned provider-visible developer contract fixture."""

    profile_id: str
    profile_version: str
    contract_id: str
    contract_version: str
    provider_tool_names: tuple[str, ...]
    rendered_text: str
    required_phrases: tuple[str, ...]
    forbidden_terms: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "provider_tool_names": list(self.provider_tool_names),
            "rendered_text": self.rendered_text,
            "required_phrases": list(self.required_phrases),
            "forbidden_terms": list(self.forbidden_terms),
        }

_CODEX_APPLY_PATCH_SPEC = ImplementLaneToolSpec(
    name="apply_patch",
    access="write",
    description=(
        "Use the `apply_patch` tool to edit files. This is a FREEFORM tool, "
        "so do not wrap the patch in JSON."
    ),
    approval_required=True,
    dry_run_supported=True,
    input_transport="json_line_array",
    preferred_bulk_argument="patch_lines",
    fallback_bulk_arguments=("patch", "input"),
    provider_native_input_kind="freeform_apply_patch",
)

_CODEX_EXEC_COMMAND_SPEC = ImplementLaneToolSpec(
    name="exec_command",
    access="execute",
    description="Runs a command, returning output or a command_id for ongoing polling.",
    approval_required=True,
)

_CODEX_WRITE_STDIN_SPEC = ImplementLaneToolSpec(
    name="write_stdin",
    access="execute",
    description=(
        "Poll an existing yielded command by short command_id with empty chars. "
        "Interactive stdin is disabled in this profile version."
    ),
)

_CODEX_LIST_DIR_SPEC = ImplementLaneToolSpec(
    name="list_dir",
    access="read",
    description="List a workspace directory with bounded entries.",
)


def codex_hot_path_tool_specs(*, enable_list_dir: bool) -> tuple[ImplementLaneToolSpec, ...]:
    """Return provider-visible specs for the Codex-like hot path profile."""

    specs = [_CODEX_APPLY_PATCH_SPEC, _CODEX_EXEC_COMMAND_SPEC, _CODEX_WRITE_STDIN_SPEC]
    if enable_list_dir:
        specs.insert(1, _CODEX_LIST_DIR_SPEC)
    return tuple(specs)


def codex_hot_path_developer_contract(
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...],
) -> DeveloperToolBehaviorContract:
    """Return the profile-owned developer contract fixture for codex_hot_path."""

    provider_tool_names = tuple(spec.name for spec in tool_specs)
    required_phrases = (
        "Use apply_patch for manual source edits.",
        "Use exec_command for inspection, builds, tests, probes, package-manager setup, and verification.",
        "Do not create or edit source files with shell heredocs, cat, printf, sed -i, perl -pi, Python file-writing scripts, or equivalent shell text-generation shortcuts.",
        "shell is not the manual source editing API.",
    )
    paragraphs = (
        "You are working through the codex_hot_path tool surface.",
        required_phrases[0],
        required_phrases[1],
        (
            f"{required_phrases[2]} Shell commands may create build outputs, run tools, "
            f"install packages when permitted, and inspect files, but {required_phrases[3]}"
        ),
        (
            "Use write_stdin only to poll or interact with an existing exec_command session "
            "according to the profile's interactive-stdin capability."
        ),
    )
    if "list_dir" in provider_tool_names:
        paragraphs += (
            "Use list_dir only for bounded directory listings; use exec_command for normal terminal inspection when shell access is available.",
        )
    return DeveloperToolBehaviorContract(
        profile_id=CODEX_HOT_PATH_PROFILE_ID,
        profile_version="v1",
        contract_id=CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID,
        contract_version=CODEX_HOT_PATH_DEVELOPER_CONTRACT_VERSION,
        provider_tool_names=provider_tool_names,
        rendered_text="\n\n".join(paragraphs),
        required_phrases=required_phrases,
        forbidden_terms=(
            "finish",
            "final_status",
            "summary",
            "evidence_refs",
            "task_done",
            "run_tests",
            "run_command",
            "read_file",
            "search_text",
            "glob",
            "inspect_dir",
            "WorkFrame",
            "next_action",
            "required_next",
            "first_write",
            "proof_manifest",
            "native_finish_gate",
            "make-doom-for-mips",
            "doomgeneric_mips",
            "/tmp/frame.bmp",
            "Terminal-Bench",
        ),
    )


def codex_hot_path_prompt_sections(
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...],
) -> tuple[PromptSection, ...]:
    """Return the Codex-like provider-visible prompt contract."""

    tool_names = {spec.name for spec in tool_specs}
    available_mutation_tools = tuple(tool for tool in ("apply_patch", "edit_file") if tool in tool_names)
    if available_mutation_tools:
        if len(available_mutation_tools) == 1:
            mutation_sentence = f"Use {available_mutation_tools[0]} for source changes. "
        else:
            mutation_sentence = f"Use {' or '.join(available_mutation_tools)} for source changes. "
        if "write_file" in tool_names:
            mutation_sentence += "Use write_file only for genuinely new files required by the task. "
    else:
        mutation_sentence = "Use the available read-only tools to inspect repository state. "
    if "exec_command" in tool_names:
        verify_sentence = "Use exec_command for builds, tests, probes, package-manager setup, and verification. "
    else:
        verify_sentence = "Use available observations to support the final response. "
    coding_contract_content = (
        "Inspect the repository, task-provided files, and recent tool results only as needed. "
        f"{mutation_sentence}"
        f"{verify_sentence}"
        "Prefer modifying or connecting provided source over fabricating replacement artifacts "
        "unless the task explicitly asks for a standalone replacement. "
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
            id="implement_v2_environment_context",
            version="v0",
            title="Implement V2 Environment Context",
            content=(
                "You are working through bounded shell tools in the task workspace. "
                "When the task runtime is a disposable benchmark or container environment "
                "and network/package-manager access is available, installing missing "
                "build, test, or toolchain packages is allowed when needed. Treat missing "
                "compiler or toolchain support as a setup/build problem to solve before "
                "replacing a requested source-based implementation. If package installation "
                "is unavailable or denied, use the concrete failure evidence instead of "
                "fabricating a replacement artifact."
            ),
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
    "CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID",
    "CODEX_HOT_PATH_DEVELOPER_CONTRACT_VERSION",
    "CODEX_HOT_PATH_PROFILE_ID",
    "CODEX_HOT_PATH_PROMPT_CONTRACT_ID",
    "DeveloperToolBehaviorContract",
    "codex_hot_path_developer_contract",
    "codex_hot_path_prompt_sections",
    "codex_hot_path_tool_specs",
]
