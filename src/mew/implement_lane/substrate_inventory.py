"""Implement v2 substrate inventory for M6.24 phase-0 checks."""

from __future__ import annotations

import argparse
from dataclasses import MISSING, fields
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .execution_evidence import (
    ARTIFACT_EVIDENCE_SCHEMA_VERSION,
    COMMAND_RUN_SCHEMA_VERSION,
    EXECUTION_CONTRACT_SCHEMA_VERSION,
    FAILURE_CLASSIFICATION_SCHEMA_VERSION,
    TOOL_RUN_RECORD_SCHEMA_VERSION,
    TYPED_ACCEPTANCE_SCHEMA_VERSION,
    VERIFIER_EVIDENCE_SCHEMA_VERSION,
)
from .tool_policy import list_v2_base_tool_specs, list_v2_tool_specs_for_mode
from .types import PROOF_MANIFEST_SCHEMA_VERSION, TOOL_CALL_SCHEMA_VERSION, TOOL_RESULT_SCHEMA_VERSION
from .workframe import (
    WORKFRAME_CANONICALIZER_VERSION,
    WORKFRAME_PHASE0_SCHEMA_VERSION,
    WORKFRAME_RED_MAX_BYTES,
    WORKFRAME_REDUCER_SCHEMA_VERSION,
    WORKFRAME_SCHEMA_VERSION,
    WORKFRAME_TARGET_MAX_BYTES,
    WorkFrameInputs,
)
from .workframe_variants import DEFAULT_WORKFRAME_VARIANT, CommonWorkFrameInputs, list_workframe_variants

INVENTORY_SCHEMA_VERSION = 1

PHASE2_INDEX_FILENAMES = (
    "tool_result_index.json",
    "evidence_ref_index.json",
    "model_turn_index.json",
)

REQUIRED_SHARED_ARTIFACTS = (
    {"filename": "tool_registry.json", "phase": 1, "surface": "tool registry artifact"},
    {"filename": "tool_policy_index.json", "phase": 1, "surface": "tool policy artifact"},
    {"filename": "natural_transcript.jsonl", "phase": 1, "surface": "natural transcript log"},
    {"filename": "tool_results.jsonl", "phase": 1, "surface": "tool result log"},
    {"filename": "tool_result_index.json", "phase": 2, "surface": "tool result index"},
    {"filename": "model_turn_index.json", "phase": 2, "surface": "model turn index"},
    {"filename": "evidence_ref_index.json", "phase": 2, "surface": "evidence ref index"},
    {"filename": "typed_evidence_delta.jsonl", "phase": 2, "surface": "typed evidence delta"},
    {"filename": "artifact_obligation_index.json", "phase": 2, "surface": "artifact obligation index"},
    {"filename": "verifier_freshness.json", "phase": 2, "surface": "verifier freshness sidecar"},
    {"filename": "repair_loop_state.json", "phase": 2, "surface": "repair loop state sidecar"},
    {"filename": "prompt_render_inventory.json", "phase": 3, "surface": "prompt render inventory"},
    {"filename": "replay_manifest.json", "phase": 6, "surface": "replay manifest"},
    {"filename": "provider_request_inventory.json", "phase": 6, "surface": "provider request inventory"},
    {"filename": "provider_response_inventory.json", "phase": 6, "surface": "provider response inventory"},
    {"filename": "workframe_variant.json", "phase": 3, "surface": "WorkFrame variant artifact"},
    {"filename": "reducer_inputs.json", "phase": 3, "surface": "reducer inputs artifact"},
    {"filename": "prompt_visible_workframe.json", "phase": 3, "surface": "prompt visible WorkFrame artifact"},
    {"filename": "reducer_output.workframe.json", "phase": 3, "surface": "reducer output artifact"},
    {"filename": "invariant_report.json", "phase": 3, "surface": "invariant report artifact"},
    {"filename": "workframe_diff.json", "phase": 6, "surface": "WorkFrame diff artifact"},
    {"filename": "workframe_cursor.json", "phase": 6, "surface": "WorkFrame cursor artifact"},
)

SHARED_SUBSTRATE_SURFACES = (
    {
        "name": "paired_tool_call_result_contract",
        "current_source": "src/mew/implement_lane/v2_runtime.py",
        "phase": 1,
        "status": "partial",
        "notes": "ToolResultEnvelope pairing exists; Phase 1 still needs explicit invariant artifacts.",
    },
    {
        "name": "natural_transcript_tool_results",
        "current_source": "src/mew/implement_lane/v2_runtime.py",
        "phase": 1,
        "status": "partial",
        "notes": "Provider-visible tool result projection exists; shared transcript-first harness is not frozen.",
    },
    {
        "name": "typed_evidence_sidecars",
        "current_source": "src/mew/implement_lane/execution_evidence.py",
        "phase": 2,
        "status": "partial",
        "notes": "Typed acceptance/evidence records exist; hot-path index files are not yet canonical artifacts.",
    },
    {
        "name": "artifact_obligations",
        "current_source": "src/mew/implement_lane/hot_path_fastcheck.py",
        "phase": 2,
        "status": "partial",
        "notes": "Finish/obligation checks exist in fastcheck fixtures; shared obligation sidecar is not frozen.",
    },
    {
        "name": "verifier_freshness",
        "current_source": "src/mew/implement_lane/workframe.py",
        "phase": 2,
        "status": "partial",
        "notes": "WorkFrame verifier state exists; canonical sidecar/index split is still pending.",
    },
    {
        "name": "repair_loop_sidecars",
        "current_source": "src/mew/implement_lane/prompt.py",
        "phase": 2,
        "status": "legacy_present",
        "notes": "Prompt projection recovery exists; redesign should demote this to sidecar-derived state.",
    },
    {
        "name": "workframe_variant_projection",
        "current_source": "src/mew/implement_lane/workframe_variants.py",
        "phase": 3,
        "status": "implemented",
        "notes": "Variant registry, CommonWorkFrameInputs wrapper, shared substrate hash, and projection hash exist.",
    },
    {
        "name": "transcript_tool_nav",
        "current_source": "",
        "phase": 4,
        "status": "missing",
        "notes": "Target variant is design-only until Phase 4.",
    },
)


def build_substrate_inventory(repo_root: Path | str = ".") -> dict[str, Any]:
    """Return the current M6.24 phase-0 inventory.

    The inventory is intentionally observational. It imports stable registry
    surfaces and inspects artifact locations, but it does not change runtime
    behavior or benchmark state.
    """

    root = Path(repo_root).resolve()
    tool_specs = [spec.as_dict() for spec in list_v2_base_tool_specs()]
    variants = [variant.__dict__.copy() for variant in list_workframe_variants()]
    proof_root = root / "proof-artifacts" / "terminal-bench"
    required_artifact_coverage = _required_artifact_coverage(proof_root)

    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "repo_root": str(root),
        "tool_registry": {
            "schema_version": 1,
            "count": len(tool_specs),
            "hash": _stable_hash(tool_specs),
            "tools": tool_specs,
            "mode_surfaces": {
                mode: [spec.name for spec in list_v2_tool_specs_for_mode(mode)]
                for mode in ("read_only", "exec", "write", "implement")
            },
        },
        "workframe_variants": {
            "default": DEFAULT_WORKFRAME_VARIANT,
            "count": len(variants),
            "hash": _stable_hash(variants),
            "variants": variants,
        },
        "schemas": {
            "tool_call": TOOL_CALL_SCHEMA_VERSION,
            "tool_result": TOOL_RESULT_SCHEMA_VERSION,
            "proof_manifest": PROOF_MANIFEST_SCHEMA_VERSION,
            "execution_contract": EXECUTION_CONTRACT_SCHEMA_VERSION,
            "command_run": COMMAND_RUN_SCHEMA_VERSION,
            "tool_run_record": TOOL_RUN_RECORD_SCHEMA_VERSION,
            "artifact_evidence": ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            "verifier_evidence": VERIFIER_EVIDENCE_SCHEMA_VERSION,
            "failure_classification": FAILURE_CLASSIFICATION_SCHEMA_VERSION,
            "typed_acceptance": TYPED_ACCEPTANCE_SCHEMA_VERSION,
            "workframe": WORKFRAME_SCHEMA_VERSION,
            "workframe_reducer": WORKFRAME_REDUCER_SCHEMA_VERSION,
            "workframe_canonicalizer": WORKFRAME_CANONICALIZER_VERSION,
            "workframe_phase0_inputs": WORKFRAME_PHASE0_SCHEMA_VERSION,
            "common_workframe_inputs": 1,
            "target_workframe_projection": 3,
        },
        "workframe_inputs": {
            "current_type": "WorkFrameInputs",
            "compatibility_wrapper_target": "CommonWorkFrameInputs",
            "compatibility_wrapper_type": CommonWorkFrameInputs.__name__,
            "fields": _dataclass_field_inventory(WorkFrameInputs),
            "migration_notes": [
                "Current WorkFrameInputs remains the source compatibility surface for existing reducers.",
                "CommonWorkFrameInputs v1 wraps current WorkFrameInputs plus tool registry, sidecars, indexes, and migration metadata.",
                "WorkFrame projection schema v3 is the target projection schema; it is distinct from CommonWorkFrameInputs schema v1.",
                "Variant projections must canonicalize CommonWorkFrameInputs before hashing or rendering.",
                "v1/v2 fixtures must be compared within their original schema or explicitly converted before v3 hash comparison.",
            ],
        },
        "byte_caps": {
            "workframe_target_max_bytes": WORKFRAME_TARGET_MAX_BYTES,
            "workframe_red_max_bytes": WORKFRAME_RED_MAX_BYTES,
        },
        "shared_substrate_surfaces": [dict(surface) for surface in SHARED_SUBSTRATE_SURFACES],
        "artifact_coverage": {
            "proof_root": str(proof_root),
            "proof_root_exists": proof_root.exists(),
            "terminal_bench_json_files": _relative_paths(root, proof_root.glob("*.json") if proof_root.exists() else ()),
            "reference_trace_exists": (proof_root / "reference-trace").exists(),
            "harbor_smoke_exists": (proof_root / "harbor-smoke").exists(),
            "required_artifact_coverage": required_artifact_coverage,
            "index_coverage": {
                name: required_artifact_coverage[name]
                for name in PHASE2_INDEX_FILENAMES
                if name in required_artifact_coverage
            },
        },
        "missing_for_offline_diagnosis": _missing_for_offline_diagnosis(required_artifact_coverage),
    }


def render_inventory_markdown(inventory: dict[str, Any]) -> str:
    """Render the inventory as a compact phase-0 Markdown artifact."""

    tool_registry = inventory["tool_registry"]
    variants = inventory["workframe_variants"]
    artifact_coverage = inventory["artifact_coverage"]
    missing = inventory["missing_for_offline_diagnosis"]
    surfaces = inventory["shared_substrate_surfaces"]

    lines = [
        "# M6.24 Phase 0 Substrate Inventory",
        "",
        "Status: generated phase-0 inventory.",
        "",
        "Purpose: record the current implement_v2 substrate before the tool-harness / WorkFrame-variant rearchitecture.",
        "",
        "## Summary",
        "",
        f"- tool registry count: `{tool_registry['count']}`",
        f"- tool registry hash: `{tool_registry['hash']}`",
        f"- WorkFrame default variant: `{variants['default']}`",
        f"- WorkFrame variant count: `{variants['count']}`",
        f"- WorkFrame variant hash: `{variants['hash']}`",
        f"- proof root exists: `{artifact_coverage['proof_root_exists']}`",
        f"- terminal-bench JSON artifact count: `{len(artifact_coverage['terminal_bench_json_files'])}`",
        f"- missing offline-diagnosis surfaces: `{len(missing)}`",
        "",
        "## Tool Surface",
        "",
        "| tool | access | approval | transport | native |",
        "|---|---|---:|---|---:|",
    ]
    for tool in tool_registry["tools"]:
        lines.append(
            "| {name} | {access} | {approval} | {transport} | {native} |".format(
                name=tool["name"],
                access=tool["access"],
                approval=str(tool["approval_required"]).lower(),
                transport=tool["input_transport"],
                native=str(tool["provider_native_eligible"]).lower(),
            )
        )

    lines.extend(
        [
            "",
            "## WorkFrame Variants",
            "",
            "| variant | description |",
            "|---|---|",
        ]
    )
    for variant in variants["variants"]:
        lines.append(f"| `{variant['name']}` | {variant['description']} |")

    lines.extend(
        [
            "",
            "## Shared Substrate Surfaces",
            "",
            "| surface | phase | status | current source | notes |",
            "|---|---:|---|---|---|",
        ]
    )
    for surface in surfaces:
        lines.append(
            "| {name} | {phase} | {status} | `{source}` | {notes} |".format(
                name=surface["name"],
                phase=surface["phase"],
                status=surface["status"],
                source=surface["current_source"] or "-",
                notes=surface["notes"],
            )
        )

    lines.extend(
        [
            "",
            "## WorkFrameInputs Compatibility Fields",
            "",
            "| field | type | default |",
            "|---|---|---|",
        ]
    )
    for field in inventory["workframe_inputs"]["fields"]:
        lines.append(f"| `{field['name']}` | `{field['type']}` | `{field['default']}` |")

    lines.extend(
        [
            "",
            "## Missing For Offline Diagnosis",
            "",
        ]
    )
    if missing:
        for item in missing:
            lines.append(
                "- `{surface}` (`{filename}`): {reason} (phase {phase})".format(
                    surface=item["surface"],
                    filename=item.get("filename", "-"),
                    reason=item["reason"],
                    phase=item["phase"],
                )
            )
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Migration Notes",
            "",
        ]
    )
    for note in inventory["workframe_inputs"]["migration_notes"]:
        lines.append(f"- {note}")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory M6.24 implement_v2 substrate surfaces.")
    parser.add_argument("--repo-root", default=".", help="Repository root to inspect.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", default="", help="Optional output file path.")
    args = parser.parse_args(argv)

    inventory = build_substrate_inventory(args.repo_root)
    if args.format == "markdown":
        rendered = render_inventory_markdown(inventory)
    else:
        rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _dataclass_field_inventory(type_: type[Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for field in fields(type_):
        items.append(
            {
                "name": field.name,
                "type": _type_name(field.type),
                "default": _field_default(field),
            }
        )
    return items


def _field_default(field: Any) -> str:
    if field.default is not MISSING:
        return repr(field.default)
    if field.default_factory is not MISSING:  # type: ignore[attr-defined]
        return "<factory>"
    return "<required>"


def _type_name(value: Any) -> str:
    return str(value).replace("typing.", "")


def _relative_paths(root: Path, paths: Iterable[Path]) -> list[str]:
    result: list[str] = []
    for path in sorted(paths):
        try:
            result.append(str(path.relative_to(root)))
        except ValueError:
            result.append(str(path))
    return result


def _required_artifact_coverage(proof_root: Path) -> dict[str, dict[str, object]]:
    coverage: dict[str, dict[str, object]] = {}
    for artifact in REQUIRED_SHARED_ARTIFACTS:
        name = str(artifact["filename"])
        matches = list(proof_root.rglob(name)) if proof_root.exists() else []
        coverage[name] = {
            "exists": bool(matches),
            "count": len(matches),
            "phase": artifact["phase"],
            "surface": artifact["surface"],
            "examples": _relative_paths(proof_root.parent.parent if proof_root.exists() else proof_root, matches[:5]),
        }
    return coverage


def _missing_for_offline_diagnosis(artifact_coverage: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    missing: list[dict[str, object]] = []
    for name, coverage in artifact_coverage.items():
        if not coverage["exists"]:
            missing.append(
                {
                    "surface": coverage["surface"],
                    "filename": name,
                    "phase": coverage["phase"],
                    "reason": "required shared artifact is not present in current proof artifacts",
                }
            )
    missing.extend(
        [
            {
                "surface": "transcript_tool_nav variant",
                "filename": "src/mew/implement_lane/workframe_variant_transcript_tool_nav.py",
                "phase": 4,
                "reason": "target variant is design-only and not registered yet",
            },
        ]
    )
    return missing


__all__ = [
    "INVENTORY_SCHEMA_VERSION",
    "PHASE2_INDEX_FILENAMES",
    "REQUIRED_SHARED_ARTIFACTS",
    "SHARED_SUBSTRATE_SURFACES",
    "build_substrate_inventory",
    "main",
    "render_inventory_markdown",
]
