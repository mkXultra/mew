"""A small deterministic adapter that should pass Phase 0 happy-path fixtures."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ..adapter_contract import adapter_manifest, default_capabilities, default_usage


class DummyPassAdapter:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._mutations: dict[str, dict[str, Any]] = {}

    def manifest(self) -> dict[str, Any]:
        return adapter_manifest(
            adapter_id="memory_eval_dummy_pass",
            memory_implementation_id="memory_eval_in_memory_dummy",
            capability_tier="retrieval_only",
            capabilities=default_capabilities(supersede=True),
        )

    def reset(self, run: Mapping[str, Any]) -> dict[str, Any]:
        self._items = {}
        self._mutations = {}
        return {"status": "success", "fixture_id": run.get("fixture_id"), "failures": []}

    def ingest(self, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        receipts = []
        for item in items:
            experience_id = str(item.get("experience_id") or "")
            self._items[experience_id] = dict(item)
            receipts.append({"experience_id": experience_id, "status": "success", "failures": []})
        return receipts

    def mutate(self, ops: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        receipts = []
        for op in ops:
            op_id = str(op.get("op_id") or "")
            self._mutations[op_id] = dict(op)
            receipts.append({"op_id": op_id, "status": "success", "failures": []})
        return receipts

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        scope_id = str(query.get("scope_id") or "")
        k = int(query.get("k") or 5)
        query_text = _query_text(query)
        candidates = []
        for item in self._items.values():
            if item.get("scope_id") != scope_id:
                continue
            visibility = item.get("visibility") or {}
            if visibility.get("retrievable") is False:
                continue
            allowed = set(visibility.get("allowed_scope_ids") or [scope_id])
            if scope_id not in allowed:
                continue
            overlap = _score_overlap(query_text, _experience_text(item))
            candidates.append((overlap, int(item.get("ingest_order") or 0), item))
        candidates.sort(key=lambda row: (-row[0], row[1], row[2].get("experience_id")))

        ranked = []
        for rank, (_, _, item) in enumerate(candidates[:k], start=1):
            experience_id = str(item.get("experience_id") or "")
            ranked.append(
                {
                    "evidence_ref": f"mem_{experience_id}",
                    "evidence_id": experience_id,
                    "rank": rank,
                    "score": None,
                    "score_type": "none",
                    "support_experience_ids": [experience_id],
                    "source_mutation_ids": [],
                    "state": "active",
                    "scope_id": item.get("scope_id"),
                }
            )
        return {
            "request_id": query.get("request_id"),
            "ranked_evidence": ranked,
            "abstained": not ranked,
            "abstained_reason": "no_memory" if not ranked else None,
            "dropped": [],
            "usage": default_usage(latency_ms=0.0),
            "failures": [],
        }

    def report_usage(self, scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return default_usage(latency_ms=0.0)


def _query_text(query: Mapping[str, Any]) -> str:
    query_block = query.get("query") or {}
    if not isinstance(query_block, Mapping):
        return ""
    return " ".join(str(query_block.get(key) or "") for key in ("text", "intent"))


def _experience_text(item: Mapping[str, Any]) -> str:
    payload = item.get("payload") or {}
    if isinstance(payload, Mapping):
        return " ".join(str(payload.get(key) or "") for key in ("text", "mime_type"))
    return str(payload)


def _score_overlap(query: str, text: str) -> int:
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    text_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
    return len(query_terms & text_terms)
