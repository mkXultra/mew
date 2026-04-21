from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Any

from .config import STATE_DIR
from .timeutil import now_iso


MEMORY_SCOPES = ("private", "team")
MEMORY_TYPES = ("user", "feedback", "project", "reference", "unknown")
CODING_MEMORY_KINDS = (
    "reviewer-steering",
    "failure-shield",
    "file-pair",
    "task-template",
    "reasoning-trace",
)
FRONTMATTER_DELIMITER = "+++"
MAX_DESCRIPTION_CHARS = 240


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    scope: str
    memory_type: str
    memory_kind: str
    name: str
    description: str
    body: str
    created_at: str
    path: Path | None = None


class FileMemoryBackend:
    def __init__(self, base_dir: Path | str = ".") -> None:
        self.base_dir = Path(base_dir)
        self.root = self.base_dir / STATE_DIR / "memory"

    def write(
        self,
        body: str,
        *,
        scope: str = "private",
        memory_type: str = "project",
        memory_kind: str = "",
        name: str = "",
        description: str = "",
        created_at: str | None = None,
    ) -> MemoryEntry:
        scope = normalize_scope(scope)
        memory_type = normalize_memory_type(memory_type)
        memory_kind = normalize_memory_kind(memory_kind, memory_type=memory_type)
        body = str(body or "").strip()
        if not body:
            raise ValueError("memory body must not be empty")
        created_at = created_at or now_iso()
        name = normalize_text(name) or first_line(body) or "Untitled memory"
        description = clip_description(description or first_line(body))
        directory = self.root / scope / memory_type
        directory.mkdir(parents=True, exist_ok=True)
        path = unique_memory_path(directory, created_at, name)
        memory_id = path.relative_to(self.root).with_suffix("").as_posix()
        entry = MemoryEntry(
            id=memory_id,
            scope=scope,
            memory_type=memory_type,
            memory_kind=memory_kind,
            name=name,
            description=description,
            body=body,
            created_at=created_at,
            path=path,
        )
        path.write_text(render_memory_entry(entry), encoding="utf-8")
        return entry

    def entries(self) -> list[MemoryEntry]:
        if not self.root.exists():
            return []
        entries: list[MemoryEntry] = []
        for path in sorted(self.root.glob("*/*/*.md")):
            if not path.is_file():
                continue
            entry = read_memory_entry(path, root=self.root)
            if entry:
                entries.append(entry)
        return entries

    def recall(
        self,
        query: str,
        *,
        scope: str | None = None,
        memory_type: str | None = None,
        memory_kind: str | None = None,
        limit: int = 5,
    ) -> list[MemoryEntry]:
        limit = max(0, int(limit or 0))
        if limit <= 0:
            return []
        scope = normalize_scope(scope) if scope else None
        memory_type = normalize_memory_type(memory_type) if memory_type else None
        memory_kind = normalize_memory_kind(memory_kind, memory_type=memory_type) if memory_kind else None
        matches = []
        for entry in self.entries():
            if scope and entry.scope != scope:
                continue
            if memory_type and entry.memory_type != memory_type:
                continue
            if memory_kind and entry.memory_kind != memory_kind:
                continue
            if memory_entry_matches(entry, query):
                matches.append(entry)
        return matches[:limit]


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def normalize_scope(value: str | None) -> str:
    normalized = normalize_text(value).casefold()
    if normalized not in MEMORY_SCOPES:
        raise ValueError(f"memory scope must be one of: {', '.join(MEMORY_SCOPES)}")
    return normalized


def normalize_memory_type(value: str | None) -> str:
    normalized = normalize_text(value).casefold()
    if normalized not in MEMORY_TYPES:
        raise ValueError(f"memory type must be one of: {', '.join(MEMORY_TYPES)}")
    return normalized


def normalize_memory_kind(value: str | None, *, memory_type: str | None = None) -> str:
    normalized = normalize_text(value).casefold()
    if not normalized:
        return ""
    normalized_type = normalize_memory_type(memory_type) if memory_type else None
    if normalized_type and normalized_type != "project":
        raise ValueError("coding memory kinds require --type project")
    if normalized not in CODING_MEMORY_KINDS:
        raise ValueError(f"memory kind must be one of: {', '.join(CODING_MEMORY_KINDS)}")
    if normalized == "reasoning-trace":
        raise ValueError("reasoning-trace is schema-only until Phase 2")
    return normalized


def first_line(value: str) -> str:
    for line in str(value or "").splitlines():
        text = normalize_text(line)
        if text:
            return text
    return ""


def clip_description(value: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", normalize_text(value).casefold()).strip("-")
    return slug or "memory"


def timestamp_slug(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", str(value or "")) or "memory"


def unique_memory_path(directory: Path, created_at: str, name: str) -> Path:
    stem = f"{timestamp_slug(created_at)}-{slugify(name)}"
    path = directory / f"{stem}.md"
    index = 2
    while path.exists():
        path = directory / f"{stem}-{index}.md"
        index += 1
    return path


def quote_frontmatter(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def parse_frontmatter_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ""
        return str(parsed) if isinstance(parsed, str) else ""
    return value.strip()


def render_memory_entry(entry: MemoryEntry) -> str:
    fields = {
        "id": entry.id,
        "scope": entry.scope,
        "type": entry.memory_type,
        "kind": entry.memory_kind,
        "name": entry.name,
        "description": entry.description,
        "created_at": entry.created_at,
    }
    lines = [FRONTMATTER_DELIMITER]
    for key, value in fields.items():
        lines.append(f"{key} = {quote_frontmatter(value)}")
    lines.extend([FRONTMATTER_DELIMITER, "", entry.body.strip(), ""])
    return "\n".join(lines)


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, text.strip()
    metadata: dict[str, str] = {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            end_index = index
            break
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            metadata[key] = parse_frontmatter_value(value)
    if end_index is None:
        return {}, text.strip()
    return metadata, "\n".join(lines[end_index + 1 :]).strip()


def read_memory_entry(path: Path, *, root: Path | None = None) -> MemoryEntry | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    metadata, body = split_frontmatter(text)
    try:
        scope = normalize_scope(metadata.get("scope") or path.parent.parent.name)
    except ValueError:
        scope = "private"
    try:
        memory_type = normalize_memory_type(metadata.get("type") or path.parent.name)
    except ValueError:
        memory_type = "unknown"
    try:
        memory_kind = normalize_memory_kind(metadata.get("kind"), memory_type=memory_type)
    except ValueError:
        memory_kind = ""
    name = normalize_text(metadata.get("name")) or path.stem
    description = clip_description(metadata.get("description") or first_line(body))
    created_at = normalize_text(metadata.get("created_at"))
    if root:
        memory_id = normalize_text(metadata.get("id")) or path.relative_to(root).with_suffix("").as_posix()
    else:
        memory_id = normalize_text(metadata.get("id")) or path.with_suffix("").as_posix()
    return MemoryEntry(
        id=memory_id,
        scope=scope,
        memory_type=memory_type,
        memory_kind=memory_kind,
        name=name,
        description=description,
        body=body,
        created_at=created_at,
        path=path,
    )


def memory_entry_matches(entry: MemoryEntry, query: str) -> bool:
    needle = normalize_text(query).casefold()
    if not needle:
        return False
    haystack = " ".join(
        [
            entry.name,
            entry.description,
            entry.body,
            entry.scope,
            entry.memory_type,
            entry.memory_kind,
        ]
    ).casefold()
    if needle in haystack:
        return True
    terms = [term for term in needle.split() if term]
    return bool(terms) and all(term in haystack for term in terms)


def entry_to_dict(entry: MemoryEntry) -> dict[str, Any]:
    data = {
        "id": entry.id,
        "scope": entry.scope,
        "memory_scope": entry.scope,
        "type": entry.memory_type,
        "memory_type": entry.memory_type,
        "memory_kind": entry.memory_kind,
        "key": entry.name,
        "name": entry.name,
        "description": entry.description,
        "text": entry.body,
        "created_at": entry.created_at,
        "storage": "file",
    }
    if entry.path:
        data["path"] = str(entry.path)
    return data
