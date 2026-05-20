from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .typed_memory import FileMemoryBackend, MemoryEntry, memory_entry_matches, normalize_text


MEMORY_PROJECTION_SECTION_ID = "implement_v2_durable_memory_projection_v0"
MEMORY_PROJECTION_SCHEMA_VERSION = "durable-memory-projection-dry-run-v0"
MEMORY_PROJECTION_CACHE_POLICY = "dynamic_uncached"
MEMORY_PROJECTION_MAX_ITEMS = 3
MEMORY_PROJECTION_MAX_CHARS = 1200
MEMORY_PROJECTION_ALLOWED_KINDS = ("reviewer-steering", "failure-shield", "file-pair")
MEMORY_PROJECTION_FORBIDDEN_KINDS = ("task-template", "reasoning-trace")
MEMORY_PROJECTION_FORBIDDEN_KEYS = (
    "next_action",
    "required_next",
    "first_write_due",
    "prewrite_probe_plateau",
    "workframe_projection",
    "finish_gate_schema",
    "proof_json",
    "reviewer_diff",
    "raw_transcript",
    "raw_reasoning_trace",
)


@dataclass(frozen=True)
class MemoryProjectionCandidate:
    entry: MemoryEntry
    status: str
    content: str = ""
    source_refs: tuple[str, ...] = ()
    drop_reason: str = ""
    details: dict[str, Any] | None = None

    def to_result(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.entry.id,
            "kind": self.entry.memory_kind,
            "name": self.entry.name,
            "status": self.status,
        }
        if self.drop_reason:
            payload["drop_reason"] = self.drop_reason
        if self.content:
            payload["content"] = self.content
            payload["chars"] = len(self.content)
        if self.source_refs:
            payload["source_refs"] = list(self.source_refs)
        if self.details:
            payload["details"] = dict(self.details)
        return payload


def durable_memory_projection_hash(items: list[dict[str, Any]]) -> str:
    encoded = json.dumps(items, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_durable_memory_projection_dry_run(
    *,
    query: str,
    base_dir: str | Path = ".",
    limit: int = 20,
    max_items: int = MEMORY_PROJECTION_MAX_ITEMS,
    max_chars: int = MEMORY_PROJECTION_MAX_CHARS,
) -> dict[str, Any]:
    """Select, revise, and size a memory projection without injecting it live."""
    max_items = min(MEMORY_PROJECTION_MAX_ITEMS, max(0, int(max_items or 0)))
    max_chars = min(MEMORY_PROJECTION_MAX_CHARS, max(0, int(max_chars or 0)))
    backend = FileMemoryBackend(base_dir)
    entries = _recall_project_memory_candidates(backend, query=query, limit=limit)
    vetoes = backend.latest_vetoes()
    revised = [
        revise_durable_memory_candidate(entry, base_dir=base_dir, veto=vetoes.get(entry.id))
        for entry in entries
    ]
    projection, budget_drops = _select_projection(revised, max_items=max_items, max_chars=max_chars)
    forbidden_scan = _scan_projected_items_for_forbidden_fields(projection)
    forbidden_drops: list[MemoryProjectionCandidate] = []
    if forbidden_scan["status"] != "passed":
        forbidden_drops = [_drop(item.entry, "forbidden_content") for item in projection]
        projection = []
    budget_drop_ids = {item.entry.id for item in budget_drops}
    forbidden_drop_ids = {item.entry.id for item in forbidden_drops}
    all_revised = [
        item
        for item in revised
        if item.entry.id not in budget_drop_ids and item.entry.id not in forbidden_drop_ids
    ]
    all_revised.extend(budget_drops)
    all_revised.extend(forbidden_drops)
    projection_items = [item.to_result() for item in projection]
    return {
        "schema_version": MEMORY_PROJECTION_SCHEMA_VERSION,
        "section_id": MEMORY_PROJECTION_SECTION_ID,
        "cache_policy": MEMORY_PROJECTION_CACHE_POLICY,
        "projection_allowed": False,
        "query": query,
        "max_items": max_items,
        "max_chars": max_chars,
        "returned_entry_ids": [entry.id for entry in entries],
        "projected_entry_ids": [item.entry.id for item in projection],
        "dropped_entry_ids_with_reason": [
            {
                "id": item.entry.id,
                "kind": item.entry.memory_kind,
                "drop_reason": item.drop_reason,
            }
            for item in all_revised
            if item.status == "dropped"
        ],
        "revise_gate_results": [item.to_result() for item in all_revised],
        "candidate_projection_chars": _projection_items_char_count(projection),
        "candidate_projection_items": projection_items,
        "projection_hash": durable_memory_projection_hash(projection_items),
        "provider_visible_forbidden_fields": forbidden_scan,
    }


def _recall_project_memory_candidates(
    backend: FileMemoryBackend,
    *,
    query: str,
    limit: int,
) -> list[MemoryEntry]:
    limit = max(0, int(limit or 0))
    if limit <= 0:
        return []
    needle = normalize_text(query)
    entries = backend.filtered_entries(scope="private", memory_type="project", include_vetoed=True)
    if needle:
        entries = [entry for entry in entries if memory_entry_matches(entry, needle)]
    return entries[:limit]


def revise_durable_memory_candidate(
    entry: MemoryEntry,
    *,
    base_dir: str | Path = ".",
    veto: dict[str, str] | None = None,
) -> MemoryProjectionCandidate:
    if veto:
        return _drop(entry, "vetoed", veto_reason=veto.get("reason") or "")
    if entry.memory_type != "project" or not entry.memory_kind:
        return _drop(entry, "schema_invalid")
    if entry.memory_kind in MEMORY_PROJECTION_FORBIDDEN_KINDS:
        return _drop(entry, "hidden_answer_risk")
    if entry.memory_kind not in MEMORY_PROJECTION_ALLOWED_KINDS:
        return _drop(entry, "schema_invalid")
    if _contains_forbidden_content(entry):
        return _drop(entry, "forbidden_content")
    if entry.memory_kind == "reviewer-steering":
        return _revise_reviewer_steering(entry)
    if entry.memory_kind == "failure-shield":
        return _revise_failure_shield(entry)
    if entry.memory_kind == "file-pair":
        return _revise_file_pair(entry, base_dir=base_dir)
    return _drop(entry, "schema_invalid")


def _revise_reviewer_steering(entry: MemoryEntry) -> MemoryProjectionCandidate:
    if not entry.approved or not entry.why or not entry.how_to_apply:
        return _drop(entry, "source_ref_missing")
    content = _one_sentence(entry.how_to_apply or entry.body)
    return _adapt(entry, content, applicability=entry.why)


def _revise_failure_shield(entry: MemoryEntry) -> MemoryProjectionCandidate:
    if not (entry.approved and entry.symptom and entry.root_cause and entry.fix and entry.stop_rule):
        return _drop(entry, "source_ref_missing")
    content = _one_sentence(f"Avoid repeating {entry.symptom}: {entry.stop_rule}. Safe repair cue: {entry.fix}.")
    return _adapt(entry, content, applicability=entry.root_cause)


def _revise_file_pair(entry: MemoryEntry, *, base_dir: str | Path) -> MemoryProjectionCandidate:
    if not (entry.source_path and entry.test_path and entry.structural_evidence and entry.focused_test_green):
        return _drop(entry, "source_ref_missing")
    missing = [path for path in (entry.source_path, entry.test_path) if not (Path(base_dir) / path).exists()]
    if missing:
        return _drop(entry, "precondition_miss", missing_paths=missing)
    content = _one_sentence(f"{entry.source_path} is paired with {entry.test_path}.")
    return _adapt(entry, content, applicability=entry.structural_evidence)


def _select_projection(
    revised: list[MemoryProjectionCandidate],
    *,
    max_items: int,
    max_chars: int,
) -> tuple[list[MemoryProjectionCandidate], list[MemoryProjectionCandidate]]:
    selected: list[MemoryProjectionCandidate] = []
    dropped: list[MemoryProjectionCandidate] = []
    for item in revised:
        if item.status != "adapted":
            continue
        if len(selected) >= max_items or _projection_items_char_count([*selected, item]) > max_chars:
            dropped.append(_drop(item.entry, "projection_budget_exceeded"))
            continue
        selected.append(item)
    return selected, dropped


def _adapt(entry: MemoryEntry, content: str, *, applicability: str) -> MemoryProjectionCandidate:
    source_refs = [entry.id]
    if entry.path:
        source_refs.append(str(entry.path))
    return MemoryProjectionCandidate(
        entry=entry,
        status="adapted",
        content=content,
        source_refs=tuple(source_refs),
        details={
            "applicability": normalize_text(applicability),
            "memory_projection_cache_policy": MEMORY_PROJECTION_CACHE_POLICY,
        },
    )


def _drop(entry: MemoryEntry, reason: str, **details: Any) -> MemoryProjectionCandidate:
    return MemoryProjectionCandidate(entry=entry, status="dropped", drop_reason=reason, details=details or None)


def _one_sentence(value: str) -> str:
    text = normalize_text(value)
    for separator in (". ", "\n", "; "):
        if separator in text:
            text = text.split(separator, 1)[0]
            break
    return text.rstrip(".") + "." if text else ""


def _contains_forbidden_content(entry: MemoryEntry) -> bool:
    haystack = " ".join(
        [
            entry.name,
            entry.body,
            entry.description,
            entry.why,
            entry.how_to_apply,
            entry.rationale,
            entry.symptom,
            entry.root_cause,
            entry.fix,
            entry.stop_rule,
            entry.situation,
            entry.reasoning,
            entry.verdict,
        ]
    ).casefold()
    return any(key.casefold() in haystack for key in MEMORY_PROJECTION_FORBIDDEN_KEYS)


def _projection_items_char_count(items: list[MemoryProjectionCandidate]) -> int:
    payload = [item.to_result() for item in items]
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _scan_projected_items_for_forbidden_fields(items: list[MemoryProjectionCandidate]) -> dict[str, Any]:
    hits = []
    rendered = json.dumps([item.to_result() for item in items], ensure_ascii=False, sort_keys=True).casefold()
    for key in MEMORY_PROJECTION_FORBIDDEN_KEYS:
        if key.casefold() in rendered:
            hits.append(key)
    return {
        "status": "failed" if hits else "passed",
        "forbidden_keys": list(MEMORY_PROJECTION_FORBIDDEN_KEYS),
        "hits": hits,
    }
