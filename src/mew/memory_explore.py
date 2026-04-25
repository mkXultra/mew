from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any

from .memory import recall_memory


HANDOFF_KEYS = (
    "target_paths",
    "cached_window_refs",
    "candidate_edit_paths",
    "exact_blockers",
    "memory_refs",
)
_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:src|tests|docs|scripts)/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)"
)
_PRIVATE_MEMORY_PREFIXES = (
    ".mew/memory/private/",
    "mew/memory/private/",
)


@dataclass
class MemoryExploreProvider:
    """Read-only in-process handoff builder for memory-backed exploration."""

    base_dir: Path | str = "."
    limit: int = 20
    file_pair_limit: int = 20

    def explore(
        self,
        state: dict[str, Any] | None = None,
        *,
        query: str = "",
        session: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        active_memory: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return filesystem-explore compatible handoff keys from memory only."""
        state = state or {}
        query_text = _query_text(query=query, session=session, task=task, active_memory=active_memory)
        effective_limit = max(0, int(self.limit if limit is None else limit))
        memory_items: list[dict[str, Any]] = []
        memory_items.extend(_active_memory_items(active_memory))
        if query_text and effective_limit:
            memory_items.extend(
                _as_dicts(
                    recall_memory(
                        state,
                        query_text,
                        limit=effective_limit,
                        base_dir=self.base_dir,
                    )
                )
            )
            memory_items.extend(
                _as_dicts(
                    recall_memory(
                        state,
                        query_text,
                        limit=max(0, int(self.file_pair_limit)),
                        memory_kind="file-pair",
                        base_dir=self.base_dir,
                    )
                )
            )
        memory_items = _dedupe_memory_items(memory_items)
        target_paths: list[str] = []
        candidate_edit_paths: list[str] = []
        cached_window_refs: list[dict[str, Any]] = []
        memory_refs: list[dict[str, Any]] = []
        for item in memory_items:
            paths = _paths_from_memory_item(item)
            for path in paths:
                _append_unique(target_paths, path)
            if _is_candidate_memory(item):
                for path in paths:
                    _append_unique(candidate_edit_paths, path)
            for ref in _cached_window_refs_from_memory_item(item):
                if ref not in cached_window_refs:
                    cached_window_refs.append(ref)
                    path = ref.get("path")
                    if isinstance(path, str):
                        normalized = _normalize_path(path)
                        if normalized:
                            _append_unique(target_paths, normalized)
                            _append_unique(candidate_edit_paths, normalized)
            memory_refs.append(_memory_ref(item))
        return {
            "target_paths": target_paths,
            "cached_window_refs": cached_window_refs,
            "candidate_edit_paths": candidate_edit_paths,
            "exact_blockers": [],
            "memory_refs": memory_refs,
        }


@dataclass(frozen=True)
class MemoryExploreHandoff:
    target_paths: list[str] = field(default_factory=list)
    cached_window_refs: list[dict[str, Any]] = field(default_factory=list)
    candidate_edit_paths: list[str] = field(default_factory=list)
    exact_blockers: list[dict[str, Any]] = field(default_factory=list)
    memory_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_paths": list(self.target_paths),
            "cached_window_refs": list(self.cached_window_refs),
            "candidate_edit_paths": list(self.candidate_edit_paths),
            "exact_blockers": list(self.exact_blockers),
            "memory_refs": list(self.memory_refs),
        }


def explore_memory(
    state: dict[str, Any] | None = None,
    *,
    query: str = "",
    session: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    active_memory: dict[str, Any] | None = None,
    base_dir: Path | str = ".",
    limit: int = 20,
) -> dict[str, Any]:
    return MemoryExploreProvider(base_dir=base_dir, limit=limit).explore(
        state,
        query=query,
        session=session,
        task=task,
        active_memory=active_memory,
        limit=limit,
    )


def _query_text(
    *,
    query: str = "",
    session: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    active_memory: dict[str, Any] | None = None,
) -> str:
    parts = [str(query or "").strip()]
    for source in (task or {}, session or {}):
        if not isinstance(source, dict):
            continue
        for key in ("title", "description", "kind", "goal"):
            value = source.get(key)
            if value:
                parts.append(str(value))
    if isinstance(active_memory, dict):
        terms = active_memory.get("terms")
        if isinstance(terms, list):
            parts.extend(str(term) for term in terms[:20] if str(term or "").strip())
    text = " ".join(part for part in parts if part)
    return " ".join(text.split())


def _active_memory_items(active_memory: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(active_memory, dict):
        return []
    return _as_dicts(active_memory.get("items") or [])


def _as_dicts(items: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items or []:
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _dedupe_memory_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = _memory_identity(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _memory_identity(item: dict[str, Any]) -> tuple[str, str]:
    for key in ("id", "path", "key", "name"):
        value = str(item.get(key) or "").strip()
        if value:
            return key, value
    return "object", repr(sorted(item.items()))


def _paths_from_memory_item(item: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("source_path", "test_path", "target_path"):
        value = item.get(key)
        if isinstance(value, str):
            _append_unique(paths, value)
    for key in ("target_paths", "candidate_edit_paths"):
        value = item.get(key)
        if isinstance(value, list):
            for path in value:
                if isinstance(path, str):
                    _append_unique(paths, path)
    text_parts = []
    for key in ("name", "key", "description", "structural_evidence", "how_to_apply", "body", "text"):
        value = item.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    for match in _PATH_RE.finditer("\n".join(text_parts)):
        _append_unique(paths, match.group(1))
    return [path for path in (_normalize_path(path) for path in paths) if path]


def _cached_window_refs_from_memory_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    refs = item.get("cached_window_refs")
    if not isinstance(refs, list):
        return []
    result: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        path = _normalize_path(str(ref.get("path") or ""))
        if not path:
            continue
        normalized = {"path": path}
        for key in ("line_start", "line_end", "line_count", "tool_call_id", "hash", "source"):
            value = ref.get(key)
            if value not in (None, ""):
                normalized[key] = value
        result.append(normalized)
    return result


def _is_candidate_memory(item: dict[str, Any]) -> bool:
    kind = str(item.get("memory_kind") or "").strip()
    if kind == "file-pair":
        return True
    if item.get("source_path") or item.get("test_path"):
        return True
    if item.get("candidate_edit_paths"):
        return True
    return False


def _memory_ref(item: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {}
    for key in (
        "id",
        "scope",
        "memory_scope",
        "type",
        "memory_type",
        "memory_kind",
        "storage",
        "score",
    ):
        value = item.get(key)
        if value not in (None, "", []):
            ref[key] = value
    for key in ("source_path", "test_path"):
        path = _normalize_path(str(item.get(key) or ""))
        if path:
            ref[key] = path
    path = _normalize_memory_ref_path(item.get("path"))
    if path:
        ref["path"] = path
    return ref


def _normalize_memory_ref_path(value: Any) -> str:
    return _normalize_path(str(value or ""))


def _normalize_path(value: str) -> str:
    path = str(value or "").strip().replace("\\", "/")
    if not path or path.startswith("/") or "\x00" in path:
        return ""
    while path.startswith("./"):
        path = path[2:]
    if re.match(r"^[A-Za-z]:/", path):
        return ""
    parts = [part for part in path.split("/") if part]
    if any(part == ".." or part.startswith("~") for part in parts):
        return ""
    if any(path.startswith(prefix) for prefix in _PRIVATE_MEMORY_PREFIXES):
        return ""
    return path


def _append_unique(items: list[str], value: str) -> None:
    normalized = _normalize_path(value)
    if normalized and normalized not in items:
        items.append(normalized)
