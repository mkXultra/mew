"""Minimal research-lane substrate fixture.

Future lanes must provide lane-owned implementations of the substrate
components carried by ``LaneRuntimeSpec``: provider adapter, tool surface
resolver, tool dispatcher, transcript store, artifact writer, completion
policy, observability policy, and optional replay validator.
"""

from __future__ import annotations

from .fixture import (
    ResearchFixtureProvider,
    ResearchFixtureRunner,
    build_research_fixture_spec,
    run_research_fixture,
    validate_research_fixture_artifacts,
)

__all__ = [
    "ResearchFixtureProvider",
    "ResearchFixtureRunner",
    "build_research_fixture_spec",
    "run_research_fixture",
    "validate_research_fixture_artifacts",
]
