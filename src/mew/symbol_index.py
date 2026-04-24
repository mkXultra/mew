from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .typed_memory import read_memory_entry

SCHEMA_VERSION = 1
INDEX_PATH = Path(".mew") / "durable" / "symbol_index.json"
MEMORY_ROOT = Path(".mew") / "memory"


def _iter_memory_files(memory_root: Path):
    if not memory_root.exists():
        return
    yield from sorted(memory_root.rglob("*.md"))


def build_symbol_index(base_dir: str | Path = ".") -> dict[str, Any]:
    root = Path(base_dir)
    memory_root = root / MEMORY_ROOT
    sources: dict[str, dict[str, Any]] = {}

    for path in _iter_memory_files(memory_root):
        entry = read_memory_entry(path, root=memory_root)
        if entry is None:
            continue
        if entry.memory_type != "project" or entry.memory_kind != "file-pair":
            continue
        source_path = str(entry.source_path or "").strip()
        test_path = str(entry.test_path or "").strip()
        if not source_path or not test_path:
            continue

        record = sources.setdefault(
            source_path,
            {
                "source_path": source_path,
                "test_path": test_path,
                "memory_ids": [],
            },
        )
        if not record.get("test_path"):
            record["test_path"] = test_path
        if entry.id and entry.id not in record["memory_ids"]:
            record["memory_ids"].append(entry.id)

    for record in sources.values():
        record["memory_ids"].sort()

    return {
        "schema_version": SCHEMA_VERSION,
        "sources": dict(sorted(sources.items())),
    }


def save_symbol_index(index: dict[str, Any], base_dir: str | Path = ".") -> Path:
    root = Path(base_dir)
    path = root / INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return path


def rebuild_symbol_index(base_dir: str | Path = ".") -> dict[str, Any]:
    index = build_symbol_index(base_dir)
    save_symbol_index(index, base_dir)
    return index


def load_symbol_index(base_dir: str | Path = ".") -> dict[str, Any]:
    path = Path(base_dir) / INDEX_PATH
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "sources": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_source_path(source_path: str, base_dir: str | Path = ".") -> dict[str, Any] | None:
    index = load_symbol_index(base_dir)
    sources = index.get("sources")
    if not isinstance(sources, dict):
        return None
    record = sources.get(str(source_path or "").strip())
    return record if isinstance(record, dict) else None


def resolve_test_path(test_path: str, base_dir: str | Path = ".") -> dict[str, Any] | None:
    index = load_symbol_index(base_dir)
    sources = index.get("sources")
    if not isinstance(sources, dict):
        return None
    wanted = str(test_path or "").strip()
    for source_path, record in sources.items():
        if not isinstance(record, dict):
            continue
        if str(record.get("test_path") or "").strip() != wanted:
            continue
        payload = dict(record)
        payload.setdefault("source_path", source_path)
        return payload
    return None
