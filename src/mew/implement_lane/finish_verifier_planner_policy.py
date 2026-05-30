"""Central default policy for the implement_v2 finish verifier planner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class FinishVerifierPlannerPolicy:
    enabled: bool
    selection_source: str
    canonical_key: str = "finish_verifier_planner_enabled"


def finish_verifier_planner_policy(
    lane_config: Mapping[str, object] | None,
) -> FinishVerifierPlannerPolicy:
    """Resolve finish verifier planner enablement from canonical config.

    The planner is default-enabled for implement_v2. The canonical
    ``finish_verifier_planner_enabled`` key wins over compatibility aliases.
    """

    config = lane_config or {}
    if "finish_verifier_planner_enabled" in config:
        enabled = _coerce_bool(config.get("finish_verifier_planner_enabled"), default=True)
        source = str(config.get("finish_verifier_planner_selection_source") or "").strip()
        if not source:
            source = "explicit_enabled" if enabled else "explicit_disabled"
        return FinishVerifierPlannerPolicy(enabled=enabled, selection_source=source)
    if "finish_verifier_planner" in config:
        enabled = _coerce_bool(config.get("finish_verifier_planner"), default=True)
        return FinishVerifierPlannerPolicy(
            enabled=enabled,
            selection_source=(
                "explicit_enabled_alias"
                if enabled
                else "explicit_disabled_legacy_alias"
            ),
        )
    if "experimental_finish_verifier_planner" in config:
        enabled = _coerce_bool(
            config.get("experimental_finish_verifier_planner"),
            default=True,
        )
        return FinishVerifierPlannerPolicy(
            enabled=enabled,
            selection_source=(
                "explicit_enabled_legacy_alias"
                if enabled
                else "explicit_disabled_legacy_alias"
            ),
        )
    return FinishVerifierPlannerPolicy(
        enabled=True,
        selection_source="default_enabled",
    )


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


__all__ = ["FinishVerifierPlannerPolicy", "finish_verifier_planner_policy"]
