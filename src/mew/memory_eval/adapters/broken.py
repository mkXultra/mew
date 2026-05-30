"""Controlled adapters that intentionally violate Phase 0 hard gates."""

from __future__ import annotations

from typing import Any, Mapping

from .dummy import DummyPassAdapter
from ..adapter_contract import default_usage


class _FixedRetrievalAdapter(DummyPassAdapter):
    adapter_id = "memory_eval_broken_fixed"

    def manifest(self) -> dict[str, Any]:
        manifest = super().manifest()
        manifest["adapter_id"] = self.adapter_id
        return manifest

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "request_id": query.get("request_id"),
            "ranked_evidence": self.ranked_evidence(query),
            "abstained": False,
            "abstained_reason": None,
            "dropped": [],
            "usage": default_usage(latency_ms=0.0),
            "failures": [],
        }

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError


class CrossScopeLeakAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_cross_scope_leak"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [_item("ex_000002", rank=1, scope_id="tenant_b/user_b")]


class CrossScopeExposureAdapter(DummyPassAdapter):
    def manifest(self) -> dict[str, Any]:
        manifest = super().manifest()
        manifest["adapter_id"] = "memory_eval_broken_cross_scope_exposure"
        return manifest

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "request_id": query.get("request_id"),
            "ranked_evidence": [],
            "abstained": True,
            "abstained_reason": "debug_drop",
            "dropped": [{"reason": "debug", "evidence_ids": ["ex_000002"]}],
            "usage": default_usage(latency_ms=0.0),
            "failures": [],
        }


class ForbiddenRetrievalAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_forbidden_retrieval"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [_item("ex_000002", rank=1, scope_id=query.get("scope_id"))]


class StaleAsFreshAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_stale_as_fresh"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [_item("ex_000001", rank=1, scope_id=query.get("scope_id"), source_mutation_ids=["mu_000001"])]


class FutureSupportAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_future_support"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [_item("ex_000002", rank=1, scope_id=query.get("scope_id"))]


class InvalidRankingAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_invalid_ranking"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [_item("ex_000001", rank=2, scope_id=query.get("scope_id"))]


class DuplicateSupportAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_duplicate_support"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            _item("ex_000001", evidence_ref="mem_first", rank=1, scope_id=query.get("scope_id")),
            _item("ex_000001", evidence_ref="mem_second", rank=2, scope_id=query.get("scope_id")),
        ]


class UnscorableEvidenceAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_unscorable_evidence"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "evidence_ref": "mem_unscorable",
                "evidence_id": None,
                "rank": 1,
                "score": None,
                "score_type": "none",
                "support_experience_ids": [],
                "source_mutation_ids": [],
                "state": "active",
                "scope_id": query.get("scope_id"),
            }
        ]


class SupportSourceMismatchAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_support_source_mismatch"

    def ranked_evidence(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        item = _item("ex_000001", rank=1, scope_id=query.get("scope_id"))
        item["source_experience_ids"] = ["ex_000002"]
        return [item]


class MissingUsageAdapter(_FixedRetrievalAdapter):
    adapter_id = "memory_eval_broken_missing_usage"

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "request_id": query.get("request_id"),
            "ranked_evidence": [_item("ex_000001", rank=1, scope_id=query.get("scope_id"))],
            "abstained": False,
            "abstained_reason": None,
            "dropped": [],
            "failures": [],
        }


def _item(
    evidence_id: str,
    *,
    evidence_ref: str | None = None,
    rank: int = 1,
    scope_id: Any = None,
    source_mutation_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_ref": evidence_ref or f"mem_{evidence_id}",
        "evidence_id": evidence_id,
        "rank": rank,
        "score": None,
        "score_type": "none",
        "support_experience_ids": [evidence_id],
        "source_mutation_ids": list(source_mutation_ids or []),
        "state": "active",
        "scope_id": scope_id,
    }
