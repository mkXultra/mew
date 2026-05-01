from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any


PROMPT_SECTION_CONTRACT_VERSION = "prompt_sections_v1"

CACHE_POLICY_CACHEABLE = "cacheable"
CACHE_POLICY_SESSION = "session"
CACHE_POLICY_DYNAMIC = "dynamic"
CACHE_POLICY_NO_CACHE = "no_cache"

STABILITY_STATIC = "static"
STABILITY_SEMI_STATIC = "semi_static"
STABILITY_DYNAMIC = "dynamic"


@dataclass(frozen=True)
class PromptSection:
    id: str
    version: str
    title: str
    content: str
    stability: str = STABILITY_STATIC
    cache_policy: str = CACHE_POLICY_CACHEABLE
    profile: str = ""


def prompt_section_hash(content: str) -> str:
    digest = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def prompt_section_cache_hint(section: PromptSection, *, in_cacheable_prefix: bool) -> str:
    if section.cache_policy == CACHE_POLICY_CACHEABLE and in_cacheable_prefix:
        return "cacheable_prefix"
    if section.cache_policy == CACHE_POLICY_CACHEABLE:
        return "cacheable_non_prefix"
    if section.cache_policy == CACHE_POLICY_SESSION:
        return "session_specific"
    if section.cache_policy == CACHE_POLICY_DYNAMIC:
        return "dynamic"
    return "no_cache"


def render_prompt_sections(sections: list[PromptSection]) -> str:
    rendered = []
    for section in sections:
        if section.id == "context_json" and section.content.startswith("Context JSON:\n"):
            # Keep Context JSON as the final raw suffix so older tests/tools can
            # still parse prompt.split("Context JSON:\n", 1)[1] as JSON.
            rendered.append(
                "\n".join(
                    [
                        (
                            f"[section:{section.id} version={section.version} "
                            f"stability={section.stability} cache_policy={section.cache_policy} "
                            f"hash={prompt_section_hash(section.content)}]"
                        ),
                        section.title,
                        f"[/section:{section.id}]",
                        section.content.rstrip(),
                    ]
                )
            )
            continue
        rendered.append(
            "\n".join(
                [
                    (
                        f"[section:{section.id} version={section.version} "
                        f"stability={section.stability} cache_policy={section.cache_policy} "
                        f"hash={prompt_section_hash(section.content)}]"
                    ),
                    section.title,
                    section.content.rstrip(),
                    f"[/section:{section.id}]",
                ]
            )
        )
    return "\n\n".join(rendered)


def prompt_section_metrics(sections: list[PromptSection]) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    total_chars = 0
    static_chars = 0
    semi_static_chars = 0
    dynamic_chars = 0
    cacheable_chars = 0
    cacheable_prefix_chars = 0
    prefix_open = True
    for index, section in enumerate(sections):
        chars = len(section.content)
        total_chars += chars
        if section.stability == STABILITY_DYNAMIC:
            dynamic_chars += chars
        elif section.stability == STABILITY_SEMI_STATIC:
            semi_static_chars += chars
        else:
            static_chars += chars
        if section.cache_policy == CACHE_POLICY_CACHEABLE:
            cacheable_chars += chars
        else:
            prefix_open = False
        if prefix_open and section.cache_policy == CACHE_POLICY_CACHEABLE:
            cacheable_prefix_chars += chars
        metrics.append(
            {
                "id": section.id,
                "index": index,
                "version": section.version,
                "title": section.title,
                "profile": section.profile,
                "chars": chars,
                "hash": prompt_section_hash(section.content),
                "stability": section.stability,
                "cache_policy": section.cache_policy,
                "cache_hint": prompt_section_cache_hint(
                    section,
                    in_cacheable_prefix=(
                        section.cache_policy == CACHE_POLICY_CACHEABLE
                        and cacheable_prefix_chars >= total_chars
                    ),
                ),
            }
        )
    return {
        "contract_version": PROMPT_SECTION_CONTRACT_VERSION,
        "section_count": len(sections),
        "total_chars": total_chars,
        "static_chars": static_chars,
        "semi_static_chars": semi_static_chars,
        "dynamic_chars": dynamic_chars,
        "cacheable_chars": cacheable_chars,
        "cacheable_prefix_chars": cacheable_prefix_chars,
        "sections": metrics,
    }
