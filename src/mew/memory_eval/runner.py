"""Phase 0 memory-eval runner skeleton."""

from __future__ import annotations

import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .adapter_contract import MemoryEvalAdapter
from .artifacts import ARTIFACT_SCHEMA_VERSION
from .fixtures import FixtureViews, find_label_leakage, load_fixture, reset_payload, split_fixture
from .hashing import stable_hash
from .scoring import (
    DEFAULT_SCORING_PROFILE,
    leakage_request_result,
    score_retrieval,
    unsupported_request_result,
)


HARNESS_ID = "mew-memory-eval"
HARNESS_VERSION = "0.1.0"
UNMAPPED_ADAPTER_REF_PREFIX = "__unmapped_adapter_ref__:"
VOLATILE_FIELDS = [
    "run_id",
    "created_at",
    "usage.latency_ms",
    "usage.cost",
    "usage.tokens.adapter_internal_input_tokens",
    "usage.tokens.adapter_internal_output_tokens",
    "environment",
]


def run_fixture(
    fixture: str | Path | Mapping[str, Any],
    adapter: MemoryEvalAdapter,
    *,
    seed: int = 12345,
    fixture_ordinal: int = 1,
    adapter_config: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    created_at: str | None = None,
    scoring_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fixture_data = load_fixture(fixture) if isinstance(fixture, (str, Path)) else dict(fixture)
    profile = dict(scoring_profile or DEFAULT_SCORING_PROFILE)
    views = split_fixture(fixture_data, fixture_ordinal=fixture_ordinal, seed=seed)
    run_id = run_id or f"run_{uuid.uuid4().hex}"
    created_at = created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest = dict(adapter.manifest())
    adapter_config_hash = stable_hash(dict(adapter_config or {}))
    manifest_hash = stable_hash(manifest)
    scoring_profile_hash = stable_hash(profile)

    leakage_failures = find_label_leakage(views.adapter_view)
    if leakage_failures:
        requests = [
            _finalize_request_hashes(
                leakage_request_result(request=request, failures=leakage_failures),
                views=views,
                request=request,
                adapter_query=_adapter_request_by_id(views, str(request.get("adapter_request_id"))),
                prefix=[],
            )
            for request in views.scorer_view["requests"]
        ]
        return _run_artifact(
            views=views,
            manifest=manifest,
            adapter_config_hash=adapter_config_hash,
            manifest_hash=manifest_hash,
            scoring_profile_hash=scoring_profile_hash,
            profile=profile,
            requests=requests,
            run_id=run_id,
            created_at=created_at,
            seed=seed,
            run_failures=leakage_failures,
        )

    adapter.reset(reset_payload(views, run_id=run_id, seed=seed))

    all_adapter_experiences = {
        str(item.get("experience_id")): item
        for item in views.adapter_view.get("experiences", [])
        if item.get("experience_id")
    }
    all_adapter_mutations = {
        str(item.get("op_id")): item for item in views.adapter_view.get("mutations", []) if item.get("op_id")
    }
    all_scorer_experiences = {
        str(item.get("experience_id")): item
        for item in views.scorer_view.get("experiences", [])
        if item.get("experience_id")
    }
    all_scorer_mutations = {
        str(item.get("op_id")): item for item in views.scorer_view.get("mutations", []) if item.get("op_id")
    }
    experience_id_to_adapter = views.id_maps.get("experience_id_to_adapter") or {}
    mutation_id_to_adapter = views.id_maps.get("mutation_id_to_adapter") or {}
    scorer_requests_by_id = {
        str(item.get("request_id")): item for item in views.scorer_view.get("requests", [])
    }
    applied_experience_ids: set[str] = set()
    applied_mutation_ids: set[str] = set()
    public_prefix: list[dict[str, Any]] = []
    request_results: list[dict[str, Any]] = []

    for operation in views.scorer_view.get("operation_sequence", []):
        operation_type = operation.get("type")
        if operation_type == "ingest":
            scorer_experience_id = str(operation.get("experience_id") or "")
            adapter_experience_id = experience_id_to_adapter.get(scorer_experience_id, scorer_experience_id)
            item = all_adapter_experiences[adapter_experience_id]
            adapter.ingest([item])
            applied_experience_ids.add(scorer_experience_id)
            public_prefix.append({"type": "ingest", "experience": item})
            continue
        if operation_type == "mutate":
            scorer_op_id = str(operation.get("op_id") or "")
            adapter_op_id = mutation_id_to_adapter.get(scorer_op_id, scorer_op_id)
            item = all_adapter_mutations[adapter_op_id]
            adapter.mutate([item])
            applied_mutation_ids.add(scorer_op_id)
            public_prefix.append({"type": "mutate", "mutation": item})
            continue
        if operation_type != "request":
            continue

        request_id = str(operation.get("request_id") or "")
        scorer_request = scorer_requests_by_id[request_id]
        adapter_query = _adapter_request_by_id(views, str(scorer_request.get("adapter_request_id")))
        missing = _missing_capabilities(scorer_request, manifest, profile)
        if missing:
            result = unsupported_request_result(
                request=scorer_request,
                missing_capabilities=missing,
                on_unsupported=str(scorer_request.get("on_unsupported") or profile.get("on_unsupported")),
            )
        else:
            started = time.perf_counter()
            retrieval = dict(adapter.retrieve(adapter_query))
            retrieval.setdefault("request_id", adapter_query.get("request_id"))
            retrieval.setdefault("ranked_evidence", [])
            retrieval.setdefault("abstained", False)
            retrieval.setdefault("dropped", [])
            retrieval.setdefault("_harness_elapsed_ms", (time.perf_counter() - started) * 1000)
            scorer_retrieval = _translate_retrieval_to_scorer_ids(retrieval, views)
            result = score_retrieval(
                request=scorer_request,
                adapter_query=adapter_query,
                retrieval=scorer_retrieval,
                manifest=manifest,
                all_experiences=all_scorer_experiences,
                applied_experience_ids=set(applied_experience_ids),
                all_mutations=all_scorer_mutations,
                applied_mutation_ids=set(applied_mutation_ids),
                profile=profile,
            )
        request_results.append(
            _finalize_request_hashes(
                result,
                views=views,
                request=scorer_request,
                adapter_query=adapter_query,
                prefix=list(public_prefix),
            )
        )

    usage = adapter.report_usage({"run_id": run_id, "fixture_id": views.adapter_fixture_id})
    artifact = _run_artifact(
        views=views,
        manifest=manifest,
        adapter_config_hash=adapter_config_hash,
        manifest_hash=manifest_hash,
        scoring_profile_hash=scoring_profile_hash,
        profile=profile,
        requests=request_results,
        run_id=run_id,
        created_at=created_at,
        seed=seed,
        usage=usage,
    )
    return artifact


def _finalize_request_hashes(
    result: dict[str, Any],
    *,
    views: FixtureViews,
    request: Mapping[str, Any],
    adapter_query: Mapping[str, Any],
    prefix: list[dict[str, Any]],
) -> dict[str, Any]:
    result = dict(result)
    result["request_hash"] = stable_hash(adapter_query)
    result["operation_prefix_hash"] = stable_hash(prefix)
    result["scope_id_hash"] = stable_hash(adapter_query.get("scope_id"))
    result["input_summary"] = {
        "k": adapter_query.get("k"),
        "max_evidence_items": (adapter_query.get("budget") or {}).get("max_evidence_items"),
        "max_latency_ms": (adapter_query.get("budget") or {}).get("max_latency_ms"),
    }
    result["fixture_request_id"] = request.get("request_id")
    return result


def _run_artifact(
    *,
    views: FixtureViews,
    manifest: Mapping[str, Any],
    adapter_config_hash: str,
    manifest_hash: str,
    scoring_profile_hash: str,
    profile: Mapping[str, Any],
    requests: list[dict[str, Any]],
    run_id: str,
    created_at: str,
    seed: int,
    usage: Mapping[str, Any] | None = None,
    run_failures: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    adapter_block = {
        "adapter_id": manifest.get("adapter_id"),
        "adapter_version": manifest.get("adapter_version"),
        "memory_implementation_id": manifest.get("memory_implementation_id"),
        "memory_implementation_version": manifest.get("memory_implementation_version"),
        "adapter_config_hash": adapter_config_hash,
        "capability_manifest_hash": manifest_hash,
        "capability_tier": manifest.get("capability_tier"),
    }
    failures = _dedupe_failures(list(run_failures or []))
    for request in requests:
        failures = _dedupe_failures([*failures, *(request.get("failures") or [])])
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "phase": views.scorer_view.get("phase") or "P0",
        "harness": {
            "harness_id": HARNESS_ID,
            "harness_version": HARNESS_VERSION,
            "scoring_profile_id": profile.get("profile_id"),
            "scoring_profile_hash": scoring_profile_hash,
        },
        "fixture": {
            "fixture_id": views.fixture_id,
            "adapter_fixture_id": views.adapter_fixture_id,
            "fixture_version": views.fixture_version,
            "fixture_public_hash": views.fixture_public_hash,
            "fixture_gold_hash": views.fixture_gold_hash,
            "fixture_full_hash": views.fixture_full_hash,
            "source_path": views.source_path,
        },
        "adapter": adapter_block,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "external_model_ids": [],
            "seed": seed,
        },
        "artifact_hashes": {},
        "volatile_fields": VOLATILE_FIELDS,
        "requests": requests,
        "aggregate_metrics": _aggregate_metrics(requests),
        "hard_gates": _aggregate_gates(requests),
        "failures": failures,
        "usage": dict(usage or {}),
    }
    deterministic_fixture = dict(artifact["fixture"])
    deterministic_fixture.pop("source_path", None)
    deterministic_subset = {
        "schema_version": artifact["schema_version"],
        "phase": artifact["phase"],
        "harness": artifact["harness"],
        "fixture": deterministic_fixture,
        "adapter": artifact["adapter"],
        "requests": _strip_request_volatile(requests),
        "aggregate_metrics": artifact["aggregate_metrics"],
        "hard_gates": artifact["hard_gates"],
        "failures": failures,
    }
    artifact["artifact_hashes"] = {
        "deterministic_result_hash": stable_hash(deterministic_subset),
        "retrieval_result_hash": stable_hash([request.get("retrieval_result_hash") for request in requests]),
        "volatile_run_hash": stable_hash(
            {
                "run_id": run_id,
                "created_at": created_at,
                "environment": artifact["environment"],
            }
        ),
        "volatile_usage_hash": stable_hash(
            {
                "request_usage": [request.get("usage") for request in requests],
                "run_usage": dict(usage or {}),
            }
        ),
    }
    return artifact


def _adapter_request_by_id(views: FixtureViews, adapter_request_id: str) -> dict[str, Any]:
    for request in views.adapter_view.get("requests", []):
        if request.get("request_id") == adapter_request_id:
            return dict(request)
    raise KeyError(f"unknown adapter request id: {adapter_request_id}")


def _translate_retrieval_to_scorer_ids(retrieval: Mapping[str, Any], views: FixtureViews) -> dict[str, Any]:
    translated = dict(retrieval)
    exp_map = views.id_maps.get("adapter_experience_id_to_scorer") or {}
    mutation_map = views.id_maps.get("adapter_mutation_id_to_scorer") or {}
    translated["ranked_evidence"] = [
        _translate_retrieval_item(item, exp_map=exp_map, mutation_map=mutation_map)
        for item in retrieval.get("ranked_evidence") or []
    ]
    translated["dropped"] = [
        _translate_visible_record(item, exp_map=exp_map)
        if isinstance(item, Mapping)
        else item
        for item in retrieval.get("dropped") or []
    ]
    translated["visible_provenance_derived_evidence_ids"] = [
        _translate_id(value, exp_map) for value in retrieval.get("visible_provenance_derived_evidence_ids") or []
    ]
    return translated


def _translate_retrieval_item(
    item: Mapping[str, Any],
    *,
    exp_map: Mapping[str, str],
    mutation_map: Mapping[str, str],
) -> dict[str, Any]:
    translated = dict(item)
    if translated.get("evidence_id"):
        translated["evidence_id"] = _translate_id(translated["evidence_id"], exp_map)
    for key in ("support_experience_ids", "source_experience_ids", "lineage_experience_ids"):
        if key in translated:
            translated[key] = [_translate_id(value, exp_map) for value in translated.get(key) or []]
    for key in ("source_mutation_ids", "support_mutation_ids"):
        if key in translated:
            translated[key] = [_translate_id(value, mutation_map) for value in translated.get(key) or []]
    return translated


def _translate_visible_record(item: Mapping[str, Any], *, exp_map: Mapping[str, str]) -> dict[str, Any]:
    translated = dict(item)
    for key in ("evidence_id", "support_experience_id", "source_experience_id"):
        if translated.get(key):
            translated[key] = _translate_id(translated[key], exp_map)
    for key in ("evidence_ids", "support_experience_ids", "source_experience_ids"):
        if key in translated:
            translated[key] = [_translate_id(value, exp_map) for value in translated.get(key) or []]
    return translated


def _translate_id(value: Any, id_map: Mapping[str, str]) -> Any:
    if value is None:
        return None
    text = str(value)
    if text in id_map:
        return id_map[text]
    return f"{UNMAPPED_ADAPTER_REF_PREFIX}{text}"


def _missing_capabilities(
    request: Mapping[str, Any],
    manifest: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> list[str]:
    capabilities = dict(manifest.get("capabilities") or {})
    required = set(profile.get("requires_capabilities") or [])
    required.update(request.get("requires_capabilities") or [])
    return sorted(capability for capability in required if not capabilities.get(capability))


def _aggregate_metrics(requests: list[dict[str, Any]]) -> dict[str, Any]:
    included = [request for request in requests if request.get("score_denominator_included")]
    status_counts: dict[str, int] = {}
    status_counts_by_mode: dict[str, dict[str, int]] = {}
    for request in requests:
        status = str(request.get("result_status") or "unknown")
        mode = str(request.get("mode") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        mode_counts = status_counts_by_mode.setdefault(mode, {})
        mode_counts[status] = mode_counts.get(status, 0) + 1
    metric_names = sorted(
        {
            metric
            for request in included
            for metric, value in (request.get("metrics") or {}).items()
            if isinstance(value, (int, float))
        }
    )
    averages = {}
    for metric in metric_names:
        values = [
            (request.get("metrics") or {}).get(metric)
            for request in included
            if isinstance((request.get("metrics") or {}).get(metric), (int, float))
        ]
        if values:
            averages[metric] = sum(values) / len(values)
    metric_averages_by_mode = {}
    for mode in sorted({str(request.get("mode") or "unknown") for request in included}):
        mode_requests = [request for request in included if str(request.get("mode") or "unknown") == mode]
        mode_averages = {}
        for metric in metric_names:
            values = [
                (request.get("metrics") or {}).get(metric)
                for request in mode_requests
                if isinstance((request.get("metrics") or {}).get(metric), (int, float))
            ]
            if values:
                mode_averages[metric] = sum(values) / len(values)
        metric_averages_by_mode[mode] = mode_averages
    return {
        "request_count": len(requests),
        "score_denominator_count": len(included),
        "status_counts": status_counts,
        "status_counts_by_mode": status_counts_by_mode,
        "metric_averages": averages,
        "metric_averages_by_mode": metric_averages_by_mode,
    }


def _aggregate_gates(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gates: dict[str, dict[str, Any]] = {}
    for request in requests:
        if not request.get("gate_denominator_included"):
            continue
        for gate in request.get("hard_gates") or []:
            gate_id = str(gate.get("gate_id") or "")
            current = gates.setdefault(gate_id, {"gate_id": gate_id, "passed": True, "failed_count": 0})
            if not gate.get("passed"):
                current["passed"] = False
                current["failed_count"] += 1
    return [gates[key] for key in sorted(gates)]


def _strip_request_volatile(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stripped = []
    for request in requests:
        item = dict(request)
        usage = item.get("usage")
        if isinstance(usage, Mapping):
            stable_usage = {
                "latency_source": ((usage.get("latency_ms") or {}).get("source")),
                "cost_methodology": ((usage.get("cost") or {}).get("methodology")),
                "token_methodology": ((usage.get("tokens") or {}).get("methodology")),
            }
            item["usage"] = stable_usage
        stripped.append(item)
    return stripped


def _dedupe_failures(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for failure in failures:
        key = str(failure.get("hash") or failure.get("failure_id") or failure)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(failure)
    return deduped
