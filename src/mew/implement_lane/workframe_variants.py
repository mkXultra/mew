"""WorkFrame reducer variant registry for implement_v2 experiments."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .workframe import WorkFrame, WorkFrameInputs, WorkFrameInvariantReport, reduce_workframe

DEFAULT_WORKFRAME_VARIANT = "current"
_VARIANT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class WorkFrameReducerVariant:
    name: str
    description: str


class UnknownWorkFrameVariantError(ValueError):
    """Raised when a requested WorkFrame reducer variant is not registered."""


_VARIANTS: dict[str, WorkFrameReducerVariant] = {
    DEFAULT_WORKFRAME_VARIANT: WorkFrameReducerVariant(
        name=DEFAULT_WORKFRAME_VARIANT,
        description="Current M6.24 WorkFrame reducer behavior.",
    ),
}


def normalize_workframe_variant(value: object) -> str:
    """Normalize a requested WorkFrame variant name."""

    text = str(value or "").strip().lower().replace("-", "_")
    return text or DEFAULT_WORKFRAME_VARIANT


def validate_workframe_variant_name(value: object) -> str:
    """Return a normalized registered WorkFrame variant name or raise."""

    name = normalize_workframe_variant(value)
    if not _VARIANT_NAME_RE.fullmatch(name):
        raise UnknownWorkFrameVariantError(f"invalid WorkFrame variant name: {value!r}")
    if name not in _VARIANTS:
        available = ", ".join(sorted(_VARIANTS))
        raise UnknownWorkFrameVariantError(f"unknown WorkFrame variant {name!r}; available: {available}")
    return name


def list_workframe_variants() -> tuple[WorkFrameReducerVariant, ...]:
    return tuple(_VARIANTS[name] for name in sorted(_VARIANTS))


def describe_workframe_variant(value: object = DEFAULT_WORKFRAME_VARIANT) -> WorkFrameReducerVariant:
    return _VARIANTS[validate_workframe_variant_name(value)]


def reduce_workframe_with_variant(
    inputs: WorkFrameInputs,
    *,
    variant: object = DEFAULT_WORKFRAME_VARIANT,
) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Reduce WorkFrame inputs with a registered variant.

    Today this registry exposes only the current reducer. The important boundary
    is intentional: future transcript-first or transition-contract experiments
    can live in separate files while sharing the same inputs, artifact format,
    fastchecks, and step-shape analyzer.
    """

    name = validate_workframe_variant_name(variant)
    if name == DEFAULT_WORKFRAME_VARIANT:
        return reduce_workframe(inputs)
    raise UnknownWorkFrameVariantError(f"unimplemented WorkFrame variant {name!r}")


__all__ = [
    "DEFAULT_WORKFRAME_VARIANT",
    "UnknownWorkFrameVariantError",
    "WorkFrameReducerVariant",
    "describe_workframe_variant",
    "list_workframe_variants",
    "normalize_workframe_variant",
    "reduce_workframe_with_variant",
    "validate_workframe_variant_name",
]
