"""Deterministic reference adapter for Phase 1 conformance fixtures."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .dummy import _experience_text, _query_text, _score_overlap
from ..adapter_contract import adapter_manifest, default_capabilities, default_usage


class ReferenceP1Adapter:
    """Small in-memory adapter for deterministic P1 fixture tests."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._mutations: dict[str, dict[str, Any]] = {}
        self._state_by_id: dict[str, str] = {}

    def manifest(self) -> dict[str, Any]:
        return adapter_manifest(
            adapter_id="memory_eval_reference_p1",
            memory_implementation_id="memory_eval_reference_in_memory",
            capability_tier="mutable_retrieval",
            capabilities=default_capabilities(
                update=True,
                delete=True,
                forget=True,
                supersede=True,
                scope_enforcement=True,
                latency_reporting=True,
            ),
        )

    def reset(self, run: Mapping[str, Any]) -> dict[str, Any]:
        self._items = {}
        self._mutations = {}
        self._state_by_id = {}
        return {"status": "success", "fixture_id": run.get("fixture_id"), "failures": []}

    def ingest(self, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        receipts = []
        for item in items:
            experience_id = str(item.get("experience_id") or "")
            self._items[experience_id] = dict(item)
            self._state_by_id[experience_id] = "active"
            receipts.append({"experience_id": experience_id, "status": "success", "failures": []})
        return receipts

    def mutate(self, ops: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        receipts = []
        for op in ops:
            op_id = str(op.get("op_id") or "")
            mutation_type = str(op.get("mutation_type") or "")
            target_id = str(op.get("target_experience_id") or "")
            replacement_id = str(op.get("replacement_experience_id") or "")
            self._mutations[op_id] = dict(op)
            if mutation_type == "supersede":
                self._set_state(target_id, "superseded")
                if replacement_id:
                    self._set_state(replacement_id, "active")
            elif mutation_type == "forget":
                self._set_state(target_id, "forgotten")
            elif mutation_type == "delete":
                self._set_state(target_id, "deleted")
            elif mutation_type == "update":
                if replacement_id:
                    self._set_state(target_id, "superseded")
                    self._set_state(replacement_id, "active")
            receipts.append({"op_id": op_id, "status": "success", "failures": []})
        return receipts

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        scope_id = str(query.get("scope_id") or "")
        k = int(query.get("k") or 5)
        budget = query.get("budget") or {}
        if budget.get("max_evidence_items") is not None:
            k = min(k, int(budget.get("max_evidence_items")))
        allowed_states = set(((query.get("filters") or {}).get("allowed_states") or ["active"]))
        query_text = _query_text(query)
        candidates = []
        for item in self._items.values():
            experience_id = str(item.get("experience_id") or "")
            state = self._state_by_id.get(experience_id, "active")
            if state not in allowed_states:
                continue
            if item.get("scope_id") != scope_id:
                continue
            visibility = item.get("visibility") or {}
            if visibility.get("retrievable") is False:
                continue
            allowed = set(visibility.get("allowed_scope_ids") or [scope_id])
            if scope_id not in allowed:
                continue
            overlap = _score_overlap(query_text, _experience_text(item))
            if overlap <= 1:
                continue
            candidates.append((overlap, int(item.get("ingest_order") or 0), item, state))
        candidates.sort(key=lambda row: (-row[0], row[1], row[2].get("experience_id")))

        ranked = []
        for rank, (_, _, item, state) in enumerate(candidates[:k], start=1):
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
                    "state": state,
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

    def _set_state(self, experience_id: str, state: str) -> None:
        if experience_id in self._items:
            self._state_by_id[experience_id] = state
