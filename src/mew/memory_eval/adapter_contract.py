"""Neutral adapter contract for the memory evaluation harness.

This module deliberately contains only harness-level schema helpers and
protocols. It must not import mew's durable memory implementation.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


MANIFEST_SCHEMA_VERSION = "memory_eval_adapter_manifest.v1"

CAPABILITY_TIERS = {
    "v0_surface",
    "retrieval_only",
    "mutable_retrieval",
    "context_optional",
    "auditable_optional",
}


class MemoryEvalAdapter(Protocol):
    def manifest(self) -> Mapping[str, Any]:
        """Return static adapter capability metadata."""

    def reset(self, run: Mapping[str, Any]) -> Mapping[str, Any]:
        """Reset adapter state for a clean fixture run."""

    def ingest(self, items: Sequence[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
        """Ingest public experiences from the fixture operation prefix."""

    def mutate(self, ops: Sequence[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
        """Apply public memory mutations from the fixture operation prefix."""

    def retrieve(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return ranked evidence for a public query without durable side effects."""

    def report_usage(self, scope: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        """Return aggregate usage for the run or requested scope."""


def default_capabilities(**overrides: bool) -> dict[str, bool]:
    capabilities = {
        "ingest": True,
        "mutate": True,
        "update": False,
        "delete": False,
        "forget": False,
        "supersede": False,
        "retrieve": True,
        "report_usage": True,
        "build_context": False,
        "inspect_provenance": False,
        "scope_enforcement": True,
        "latency_reporting": True,
        "cost_reporting": False,
        "deterministic_seed": True,
    }
    capabilities.update(overrides)
    return capabilities


def adapter_manifest(
    *,
    adapter_id: str,
    adapter_version: str = "0.1.0",
    memory_implementation_id: str = "memory_eval_dummy",
    memory_implementation_version: str = "0.1.0",
    capability_tier: str = "retrieval_only",
    capabilities: Mapping[str, bool] | None = None,
    limits: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if capability_tier not in CAPABILITY_TIERS:
        raise ValueError(f"unknown capability tier: {capability_tier}")
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "memory_implementation_id": memory_implementation_id,
        "memory_implementation_version": memory_implementation_version,
        "capability_tier": capability_tier,
        "capabilities": dict(capabilities or default_capabilities()),
        "limits": {
            "max_payload_bytes": None,
            "max_k": None,
            "max_fixture_items": None,
            **dict(limits or {}),
        },
    }


def default_usage(*, latency_ms: float | None = 0.0) -> dict[str, Any]:
    return {
        "latency_ms": {
            "retrieve": latency_ms,
            "total": latency_ms,
            "source": "harness_measured",
        },
        "tokens": {
            "adapter_internal_input_tokens": None,
            "adapter_internal_output_tokens": None,
            "methodology": "not_reported",
        },
        "cost": {
            "cost_units": None,
            "currency": None,
            "methodology": "not_reported",
        },
    }
