"""Legacy model-JSON provider adapter surface for implement_v2 replay/runtime."""

from __future__ import annotations

from .provider import FakeProviderAdapter


class JsonModelProviderAdapter(FakeProviderAdapter):
    """Provider adapter for the quarantined legacy model-JSON transport."""

    provider = "model_json"


__all__ = ["JsonModelProviderAdapter"]
