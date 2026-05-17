"""Profile-owned provider-visible tool surfaces and prompt contracts."""

from .codex_hot_path import (
    CODEX_HOT_PATH_PROFILE_ID,
    CODEX_HOT_PATH_PROMPT_CONTRACT_ID,
    codex_hot_path_prompt_sections,
    codex_hot_path_tool_specs,
)
from .mew_legacy import (
    MEW_LEGACY_PROFILE_ID,
    MEW_LEGACY_PROMPT_CONTRACT_ID,
    MEW_LEGACY_TOOL_SPECS,
    mew_legacy_prompt_sections,
    mew_legacy_tool_specs_for_mode,
    mew_legacy_tool_specs_for_task,
)
from .prompt_contracts import (
    prompt_contract_id_for_profile,
    prompt_sections_for_tool_surface,
)

__all__ = [
    "CODEX_HOT_PATH_PROFILE_ID",
    "CODEX_HOT_PATH_PROMPT_CONTRACT_ID",
    "MEW_LEGACY_PROFILE_ID",
    "MEW_LEGACY_PROMPT_CONTRACT_ID",
    "MEW_LEGACY_TOOL_SPECS",
    "codex_hot_path_prompt_sections",
    "codex_hot_path_tool_specs",
    "mew_legacy_prompt_sections",
    "mew_legacy_tool_specs_for_mode",
    "mew_legacy_tool_specs_for_task",
    "prompt_contract_id_for_profile",
    "prompt_sections_for_tool_surface",
]
