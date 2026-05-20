"""Explicit legacy model-JSON implement_v2 runtime surface.

This module is the quarantined import path for historical model-JSON live-loop
tests, replay readers, and diagnostics. Production native implement_v2 code
must import provider-native helpers instead of this module.
"""

from __future__ import annotations

from .v2_runtime import (
    _frontier_evidence_registry,
    _render_prompt_history_json,
    _source_output_contract_from_tool_results,
    run_live_json_implement_v2,
    run_unavailable_implement_v2,
)


__all__ = [
    "_frontier_evidence_registry",
    "_render_prompt_history_json",
    "_source_output_contract_from_tool_results",
    "run_live_json_implement_v2",
    "run_unavailable_implement_v2",
]
