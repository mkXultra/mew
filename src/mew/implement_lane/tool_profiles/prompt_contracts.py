"""Profile-owned prompt contract catalog for implement_v2 tool surfaces."""

from __future__ import annotations

from ...prompt_sections import PromptSection
from ..tool_specs import ImplementLaneToolSpec
from .codex_hot_path import (
    CODEX_HOT_PATH_PROFILE_ID,
    CODEX_HOT_PATH_PROMPT_CONTRACT_ID,
    codex_hot_path_prompt_sections,
)
from .mew_legacy import (
    MEW_LEGACY_PROFILE_ID,
    MEW_LEGACY_PROMPT_CONTRACT_ID,
    mew_legacy_prompt_sections,
)


def prompt_contract_id_for_profile(profile_id: str) -> str:
    """Return the immutable prompt contract id for a known profile."""

    if profile_id == CODEX_HOT_PATH_PROFILE_ID:
        return CODEX_HOT_PATH_PROMPT_CONTRACT_ID
    if profile_id == MEW_LEGACY_PROFILE_ID:
        return MEW_LEGACY_PROMPT_CONTRACT_ID
    raise ValueError(f"unsupported tool_surface_profile_id: {profile_id}")


def prompt_sections_for_tool_surface(
    *,
    profile_id: str,
    prompt_contract_id: str,
    tool_specs: tuple[ImplementLaneToolSpec, ...],
    task_contract_content: str,
) -> tuple[PromptSection, ...]:
    """Return prompt sections owned by the selected tool-surface profile."""

    if profile_id == CODEX_HOT_PATH_PROFILE_ID:
        if prompt_contract_id != CODEX_HOT_PATH_PROMPT_CONTRACT_ID:
            raise ValueError(f"unsupported codex_hot_path prompt contract: {prompt_contract_id}")
        return codex_hot_path_prompt_sections(tool_specs=tool_specs)
    if profile_id == MEW_LEGACY_PROFILE_ID:
        if prompt_contract_id != MEW_LEGACY_PROMPT_CONTRACT_ID:
            raise ValueError(f"unsupported mew_legacy prompt contract: {prompt_contract_id}")
        return mew_legacy_prompt_sections(
            tool_specs=tool_specs,
            task_contract_content=task_contract_content,
        )
    raise ValueError(f"unsupported tool_surface_profile_id: {profile_id}")


__all__ = [
    "prompt_contract_id_for_profile",
    "prompt_sections_for_tool_surface",
]
