"""Deterministic Phase 0/P1-compatible retrieval scoring."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .artifacts import gate_result, make_failure
from .hashing import stable_hash


DEFAULT_SCORING_PROFILE = {
    "schema_version": "memory_eval_scoring_profile.v1",
    "profile_id": "m6_25_phase0_conformance_v1",
    "phase": "P0",
    "metric_cutoffs": {
        "dummy_happy_path": {
            "recall_at_k_min": 1.0,
            "mrr_at_k_min": 1.0,
        },
        "retrieval_ranking": {
            "recall_at_k_min": 1.0,
            "mrr_at_k_min": 0.5,
            "ndcg_at_k_min": 0.75,
        },
        "budget_limited": {
            "recall_at_k_min": 1.0,
            "mrr_at_k_min": 1.0,
        },
    },
    "hard_gates": [
        "no_cross_scope_leak",
        "no_cross_scope_exposure",
        "no_forbidden_retrieval",
        "no_stale_as_fresh_when_strict",
        "no_contradiction_as_fresh_when_strict",
        "abstention_matches_expected",
        "item_budget_respected",
        "required_usage_present",
        "valid_rank_ordering",
        "no_unknown_or_future_support_refs",
        "required_support_mapping_present",
        "relevant_support_present",
        "support_source_consistency",
        "no_duplicate_support_reference",
        "required_capability_supported",
        "no_label_leakage",
    ],
    "requires_capabilities": ["retrieve"],
    "on_unsupported": "hard_failure",
    "hard_latency_budget": False,
    "hard_cost_budget": False,
    "aggregation": {
        "group_by": ["mode", "fixture_family", "capability_tier"],
        "single_score": False,
        "include_not_applicable_in_denominator": False,
    },
}


def score_retrieval(
    *,
    request: Mapping[str, Any],
    adapter_query: Mapping[str, Any],
    retrieval: Mapping[str, Any],
    manifest: Mapping[str, Any],
    all_experiences: Mapping[str, Mapping[str, Any]],
    applied_experience_ids: set[str],
    all_mutations: Mapping[str, Mapping[str, Any]],
    applied_mutation_ids: set[str],
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    profile = profile or DEFAULT_SCORING_PROFILE
    failures: list[dict[str, Any]] = []
    hard_gates: list[dict[str, Any]] = []
    gold = dict(request.get("gold") or {})
    request_id = str(request.get("request_id") or "")
    adapter_request_id = str(request.get("adapter_request_id") or adapter_query.get("request_id") or "")
    ranked = list(retrieval.get("ranked_evidence") or [])
    k = int(adapter_query.get("k") or 0)
    budget = dict(adapter_query.get("budget") or {})
    max_items = budget.get("max_evidence_items")
    item_limit = min(k, int(max_items)) if max_items is not None else k
    authorized_scope_ids = _authorized_scope_ids(gold, adapter_query=adapter_query, request=request)

    returned = []
    scorable_union: list[str] = []
    visible_exposure_ids: list[str] = []
    item_relevance: list[int] = []
    support_signatures: dict[tuple[str, ...], int] = {}
    returned_identities: set[str] = set()

    for index, item in enumerate(ranked, start=1):
        item = dict(item)
        support_ids = scorable_support_ids(item)
        identity = returned_item_identity(item)
        source_mutation_ids = [str(value) for value in (item.get("source_mutation_ids") or [])]
        support_mutation_ids = [str(value) for value in (item.get("support_mutation_ids") or [])]
        artifact_item = {
            "evidence_ref": item.get("evidence_ref"),
            "evidence_id": item.get("evidence_id"),
            "rank": item.get("rank"),
            "score": item.get("score"),
            "score_type": item.get("score_type") or "none",
            "support_experience_ids": list(item.get("support_experience_ids") or []),
            "source_experience_ids": list(item.get("source_experience_ids") or []),
            "source_mutation_ids": source_mutation_ids,
            "support_mutation_ids": support_mutation_ids,
            "scorable_support_ids": support_ids,
            "state_reported_by_adapter": item.get("state"),
            "scope_id_hash": stable_hash(item.get("scope_id")),
        }
        debug_metadata = _artifact_debug_metadata(item.get("metadata"))
        if debug_metadata:
            artifact_item["debug_metadata"] = debug_metadata
        returned.append(artifact_item)
        scorable_union.extend(support_ids)

        rank = item.get("rank")
        if rank != index:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="invalid_ranking",
                    message=f"Returned rank {rank!r} at position {index}, expected {index}.",
                    request_id=request_id,
                    gate_id="valid_rank_ordering",
                    expected=index,
                    actual=rank,
                )
            )
        if not identity:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="invalid_ranking",
                    message="Returned item has neither evidence_ref nor evidence_id.",
                    request_id=request_id,
                    gate_id="valid_rank_ordering",
                    expected="non-empty returned item identity",
                    actual=None,
                )
            )
        elif identity in returned_identities:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="invalid_ranking",
                    message=f"Returned duplicate evidence identity {identity}.",
                    request_id=request_id,
                    evidence_id=item.get("evidence_id"),
                    gate_id="valid_rank_ordering",
                    expected="unique returned item identities",
                    actual=identity,
                )
            )
        returned_identities.add(identity)

        support_values = set(str(value) for value in item.get("support_experience_ids") or [])
        source_values = set(str(value) for value in item.get("source_experience_ids") or [])
        if support_values and source_values and support_values != source_values:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="support_source_mismatch",
                    message="support_experience_ids and source_experience_ids differ.",
                    request_id=request_id,
                    evidence_id=item.get("evidence_id"),
                    gate_id="support_source_consistency",
                    expected=sorted(support_values),
                    actual=sorted(source_values),
                )
            )

        if not support_ids:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="unscorable_evidence",
                    message="Returned item has no scorable support IDs.",
                    request_id=request_id,
                    evidence_id=item.get("evidence_id"),
                    gate_id="required_support_mapping_present",
                    expected="non-empty scorable_support_ids",
                    actual=[],
                )
            )

        signature = tuple(sorted(support_ids))
        if signature:
            if signature in support_signatures:
                failures.append(
                    make_failure(
                        stage="scoring",
                        type="duplicate_support_reference",
                        message=f"Returned duplicate support signature {list(signature)}.",
                        request_id=request_id,
                        evidence_id=item.get("evidence_id"),
                        gate_id="no_duplicate_support_reference",
                        expected="unique non-empty support signatures",
                        actual=list(signature),
                    )
                )
            support_signatures[signature] = index

        for support_id in support_ids:
            failures.extend(
                _validate_experience_ref(
                    support_id,
                    request_id=request_id,
                    applied_experience_ids=applied_experience_ids,
                    all_experiences=all_experiences,
                )
            )
        for mutation_id in [*source_mutation_ids, *support_mutation_ids]:
            failures.extend(
                _validate_mutation_ref(
                    mutation_id,
                    request_id=request_id,
                    applied_mutation_ids=applied_mutation_ids,
                    all_mutations=all_mutations,
                )
            )

        item_relevance.append(1 if set(support_ids) & set(gold.get("relevant_evidence_ids") or []) else 0)

    if len(ranked) > item_limit:
        failures.append(
            make_failure(
                stage="scoring",
                type="budget_violation",
                message=f"Returned {len(ranked)} items, exceeding item budget {item_limit}.",
                request_id=request_id,
                gate_id="item_budget_respected",
                metric_id="budget_violation",
                expected=item_limit,
                actual=len(ranked),
            )
        )

    explicit_visible_exposure_ids = _visible_exposure_ids(retrieval)
    for evidence_id in explicit_visible_exposure_ids:
        failures.extend(
            _validate_experience_ref(
                evidence_id,
                request_id=request_id,
                applied_experience_ids=applied_experience_ids,
                all_experiences=all_experiences,
            )
        )
    visible_exposure_ids.extend(explicit_visible_exposure_ids)
    visible_exposure_ids.extend(scorable_union)

    failures.extend(
        _scope_failures(
            request_id=request_id,
            gate_id="no_cross_scope_leak",
            metric_id="cross_scope_leak_rate",
            evidence_ids=scorable_union,
            request_scope=str(adapter_query.get("scope_id") or request.get("scope_id") or ""),
            all_experiences=all_experiences,
            authorized_scope_ids=authorized_scope_ids,
            failure_type="cross_scope_leak",
            message_prefix="Returned evidence",
        )
    )
    failures.extend(
        _scope_failures(
            request_id=request_id,
            gate_id="no_cross_scope_exposure",
            metric_id="cross_scope_exposure_rate",
            evidence_ids=visible_exposure_ids,
            request_scope=str(adapter_query.get("scope_id") or request.get("scope_id") or ""),
            all_experiences=all_experiences,
            authorized_scope_ids=authorized_scope_ids,
            failure_type="cross_scope_leak",
            message_prefix="Caller-visible evidence",
        )
    )

    forbidden_ids = set(gold.get("must_not_return_evidence_ids") or [])
    relevant_ids = set(gold.get("relevant_evidence_ids") or [])
    for evidence_id in sorted(set(scorable_union) & forbidden_ids):
        failures.append(
            make_failure(
                stage="scoring",
                type="forbidden_retrieval",
                message=f"Returned forbidden evidence {evidence_id}.",
                request_id=request_id,
                evidence_id=evidence_id,
                gate_id="no_forbidden_retrieval",
                metric_id="forbidden_retrieval_rate",
                expected=0,
                actual=1,
            )
        )

    relevant_support_ids = set(scorable_union) & relevant_ids
    if relevant_ids and not relevant_support_ids:
        failures.append(
            make_failure(
                stage="scoring",
                type="missing_relevant_support",
                message="Answerable request returned no relevant support.",
                request_id=request_id,
                gate_id="relevant_support_present",
                metric_id="recall_at_k",
                expected=sorted(relevant_ids),
                actual=sorted(set(scorable_union)),
            )
        )

    stale_ids = set(gold.get("stale_evidence_ids") or [])
    if gold.get("strict_stale", bool(stale_ids)):
        for evidence_id in sorted(set(scorable_union) & stale_ids):
            failures.append(
                make_failure(
                    stage="scoring",
                    type="stale_as_fresh",
                    message=f"Returned stale evidence {evidence_id} as fresh support.",
                    request_id=request_id,
                    evidence_id=evidence_id,
                    gate_id="no_stale_as_fresh_when_strict",
                    metric_id="stale_as_fresh",
                    expected=0,
                    actual=1,
                )
            )

    for conflict in gold.get("conflict_sets") or []:
        stale_present = set(conflict.get("stale_ids") or []) & set(scorable_union)
        fresh_present = set(conflict.get("fresh_ids") or []) & set(scorable_union)
        if stale_present and fresh_present:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="contradiction_as_fresh",
                    message="Returned stale and fresh evidence from the same conflict set.",
                    request_id=request_id,
                    gate_id="no_contradiction_as_fresh_when_strict",
                    metric_id="contradiction_as_fresh",
                    expected=0,
                    actual={"stale": sorted(stale_present), "fresh": sorted(fresh_present)},
                )
            )

    expected_abstention = gold.get("expected_abstention")
    actual_abstention = bool(retrieval.get("abstained"))
    if expected_abstention is True and (not actual_abstention or scorable_union):
        failures.append(
            make_failure(
                stage="scoring",
                type="abstention_mismatch",
                message="Expected abstention, but adapter returned supporting memory.",
                request_id=request_id,
                gate_id="abstention_matches_expected",
                metric_id="abstention_correct",
                expected=True,
                actual={"abstained": actual_abstention, "support_ids": sorted(set(scorable_union))},
            )
        )
    if expected_abstention is False and actual_abstention and not gold.get("allow_false_abstention"):
        failures.append(
            make_failure(
                stage="scoring",
                type="abstention_mismatch",
                message="Adapter abstained on an answerable request.",
                request_id=request_id,
                gate_id="abstention_matches_expected",
                metric_id="abstention_correct",
                expected=False,
                actual=True,
            )
        )

    if _requires_latency(manifest) and not _has_latency_usage(retrieval):
        failures.append(
            make_failure(
                stage="retrieve",
                type="missing_usage",
                message="Adapter manifest declares latency reporting but retrieve usage is missing.",
                request_id=request_id,
                gate_id="required_usage_present",
                expected="usage.latency_ms.retrieve",
                actual=retrieval.get("usage"),
                adapter_status=str(retrieval.get("status") or "success"),
            )
        )

    expected_usage = gold.get("expected_usage") if isinstance(gold.get("expected_usage"), Mapping) else {}
    expected_usage_failures = _expected_usage_failures(
        request_id=request_id,
        expected=expected_usage,
        retrieval=retrieval,
    )
    failures.extend(expected_usage_failures)
    expected_dropped_counts = (
        gold.get("expected_dropped_count_by_reason")
        if isinstance(gold.get("expected_dropped_count_by_reason"), Mapping)
        else {}
    )
    expected_dropped_count_failures = _expected_dropped_count_failures(
        request_id=request_id,
        expected=expected_dropped_counts,
        retrieval=retrieval,
    )
    failures.extend(expected_dropped_count_failures)
    expected_graph_verification = (
        gold.get("expected_derived_graph_index_verification")
        if isinstance(gold.get("expected_derived_graph_index_verification"), Mapping)
        else {}
    )
    expected_graph_verification_failures = _expected_graph_verification_failures(
        request_id=request_id,
        expected=expected_graph_verification,
        retrieval=retrieval,
    )
    failures.extend(expected_graph_verification_failures)

    metrics = _metrics(
        returned_count=len(ranked),
        k=k,
        item_relevance=item_relevance,
        support_ids=scorable_union,
        exposure_ids=visible_exposure_ids,
        relevant_ids=relevant_ids,
        stale_ids=stale_ids,
        conflict_sets=list(gold.get("conflict_sets") or []),
        forbidden_ids=forbidden_ids,
        all_experiences=all_experiences,
        request_scope=str(adapter_query.get("scope_id") or request.get("scope_id") or ""),
        authorized_scope_ids=authorized_scope_ids,
        expected_abstention=expected_abstention,
        actual_abstention=actual_abstention,
        item_limit=item_limit,
    )
    if expected_usage:
        metrics["expected_usage_satisfied"] = 0.0 if expected_usage_failures else 1.0
    if expected_dropped_counts:
        metrics["expected_dropped_counts_satisfied"] = 0.0 if expected_dropped_count_failures else 1.0
    if expected_graph_verification:
        metrics["expected_derived_graph_index_verification_satisfied"] = (
            0.0 if expected_graph_verification_failures else 1.0
        )
    failures.extend(_threshold_failures(request=request, metrics=metrics, profile=profile))

    gate_ids = list(profile.get("hard_gates") or [])
    if expected_usage and "expected_usage_satisfied" not in gate_ids:
        gate_ids.append("expected_usage_satisfied")
    if expected_dropped_counts and "expected_dropped_counts_satisfied" not in gate_ids:
        gate_ids.append("expected_dropped_counts_satisfied")
    if expected_graph_verification and "expected_derived_graph_index_verification_satisfied" not in gate_ids:
        gate_ids.append("expected_derived_graph_index_verification_satisfied")
    profile_gate_ids = set(gate_ids)
    gate_ids.extend(
        sorted(
            {
                str(failure.get("gate_id"))
                for failure in failures
                if failure.get("gate_id") and str(failure.get("gate_id")) not in profile_gate_ids
            }
        )
    )
    for gate_id in gate_ids:
        related = [failure for failure in failures if failure.get("gate_id") == gate_id]
        if related:
            hard_gates.append(gate_result(gate_id, False, related[0]["message"]))
        else:
            hard_gates.append(gate_result(gate_id, True, "No failure for gate."))

    retrieval_artifact = {
        "returned_evidence_order": returned,
        "abstained": actual_abstention,
        "abstained_reason": retrieval.get("abstained_reason"),
        "visible_dropped": list(retrieval.get("dropped") or []),
        "dropped_count_by_reason": dict(retrieval.get("dropped_count_by_reason") or {}),
        "derived_graph_index_verification": dict(retrieval.get("derived_graph_index_verification") or {}),
        "visible_provenance_derived_evidence_ids": list(
            retrieval.get("visible_provenance_derived_evidence_ids") or []
        ),
        "hash_usage_fields": {
            "latency_source": ((retrieval.get("usage") or {}).get("latency_ms") or {}).get("source"),
            "cost_methodology": ((retrieval.get("usage") or {}).get("cost") or {}).get("methodology"),
            "token_methodology": ((retrieval.get("usage") or {}).get("tokens") or {}).get("methodology"),
        },
    }
    retrieval_result_hash = retrieval_result_hash_input_hash(retrieval_artifact)
    status = "failed" if any(failure.get("severity") == "error" for failure in failures) else "passed"
    expected_failure_types = set(str(value) for value in (request.get("expected_failure_types") or []))
    observed_error_types = {str(failure.get("type")) for failure in failures if failure.get("severity") == "error"}
    if expected_failure_types and observed_error_types == expected_failure_types:
        status = "expected_failure"
    return {
        "request_id": request_id,
        "adapter_request_id": adapter_request_id,
        "result_status": status,
        "score_denominator_included": status in {"passed", "failed"},
        "gate_denominator_included": status in {"passed", "failed"},
        "unsupported_capabilities": [],
        "status_reason": _status_reason(status, expected_failure_types=expected_failure_types),
        "mode": request.get("mode"),
        "retrieval": retrieval_artifact,
        "usage": retrieval.get("usage"),
        "metrics": metrics,
        "hard_gates": hard_gates,
        "failures": failures,
        "retrieval_result_hash": retrieval_result_hash,
    }


def unsupported_request_result(
    *,
    request: Mapping[str, Any],
    missing_capabilities: list[str],
    on_unsupported: str,
) -> dict[str, Any]:
    if on_unsupported == "not_applicable":
        status = "not_applicable"
    elif on_unsupported == "expected_failure":
        status = "expected_failure"
    else:
        status = "failed"
    failure = make_failure(
        stage="retrieve",
        type="unsupported_capability",
        message=f"Adapter lacks required capabilities: {', '.join(missing_capabilities)}.",
        request_id=str(request.get("request_id") or ""),
        gate_id="required_capability_supported",
        expected={capability: True for capability in missing_capabilities},
        actual={capability: False for capability in missing_capabilities},
        adapter_status="unsupported",
        severity="info" if status in {"not_applicable", "expected_failure"} else "error",
    )
    return {
        "request_id": request.get("request_id"),
        "adapter_request_id": request.get("adapter_request_id"),
        "result_status": status,
        "score_denominator_included": status == "failed",
        "gate_denominator_included": status == "failed",
        "unsupported_capabilities": missing_capabilities,
        "status_reason": failure["message"],
        "mode": request.get("mode"),
        "retrieval": {
            "returned_evidence_order": [],
            "abstained": False,
            "abstained_reason": None,
            "visible_dropped": [],
            "dropped_count_by_reason": {},
            "derived_graph_index_verification": {},
            "visible_provenance_derived_evidence_ids": [],
            "hash_usage_fields": {},
        },
        "usage": None,
        "metrics": {},
        "hard_gates": [
            gate_result("required_capability_supported", status in {"not_applicable", "expected_failure"}, failure["message"])
        ],
        "failures": [failure],
        "retrieval_result_hash": stable_hash({"unsupported": missing_capabilities, "status": status}),
    }


def leakage_request_result(*, request: Mapping[str, Any], failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "request_id": request.get("request_id"),
        "adapter_request_id": request.get("adapter_request_id"),
        "result_status": "failed",
        "score_denominator_included": True,
        "gate_denominator_included": True,
        "unsupported_capabilities": [],
        "status_reason": "Adapter view label leakage detected.",
        "mode": request.get("mode"),
        "retrieval": {
            "returned_evidence_order": [],
            "abstained": False,
            "abstained_reason": None,
            "visible_dropped": [],
            "dropped_count_by_reason": {},
            "derived_graph_index_verification": {},
            "visible_provenance_derived_evidence_ids": [],
            "hash_usage_fields": {},
        },
        "usage": None,
        "metrics": {},
        "hard_gates": [gate_result("no_label_leakage", False, failures[0]["message"])],
        "failures": failures,
        "retrieval_result_hash": stable_hash({"label_leakage": [failure["hash"] for failure in failures]}),
    }


def retrieval_result_hash_input_hash(retrieval_artifact: Mapping[str, Any]) -> str:
    return stable_hash(
        {
            "returned_evidence_order": retrieval_artifact.get("returned_evidence_order") or [],
            "abstained": retrieval_artifact.get("abstained"),
            "abstained_reason": retrieval_artifact.get("abstained_reason"),
            "visible_dropped": retrieval_artifact.get("visible_dropped") or [],
            "dropped_count_by_reason": retrieval_artifact.get("dropped_count_by_reason") or {},
            "visible_provenance_derived_evidence_ids": retrieval_artifact.get(
                "visible_provenance_derived_evidence_ids"
            )
            or [],
            "hash_usage_fields": retrieval_artifact.get("hash_usage_fields") or {},
        }
    )


def scorable_support_ids(item: Mapping[str, Any]) -> list[str]:
    support = [str(value) for value in (item.get("support_experience_ids") or []) if str(value)]
    if support:
        return support
    source = [str(value) for value in (item.get("source_experience_ids") or []) if str(value)]
    if source:
        return source
    evidence_id = item.get("evidence_id")
    if evidence_id:
        return [str(evidence_id)]
    return []


def returned_item_identity(item: Mapping[str, Any]) -> str:
    return str(item.get("evidence_ref") or item.get("evidence_id") or "")


def _validate_experience_ref(
    evidence_id: str,
    *,
    request_id: str,
    applied_experience_ids: set[str],
    all_experiences: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not evidence_id:
        return [
            make_failure(
                stage="scoring",
                type="invalid_support_reference",
                message="Support reference is empty.",
                request_id=request_id,
                evidence_id=evidence_id,
                gate_id="no_unknown_or_future_support_refs",
                expected="non-empty support ID",
                actual=evidence_id,
            )
        ]
    if evidence_id not in all_experiences:
        return [
            make_failure(
                stage="scoring",
                type="unknown_evidence_reference",
                message=f"Support reference {evidence_id} is not in fixture public experiences.",
                request_id=request_id,
                evidence_id=evidence_id,
                gate_id="no_unknown_or_future_support_refs",
                expected="known public experience ID",
                actual=evidence_id,
            )
        ]
    if evidence_id not in applied_experience_ids:
        return [
            make_failure(
                stage="scoring",
                type="future_evidence_reference",
                message=f"Support reference {evidence_id} is after the request prefix.",
                request_id=request_id,
                evidence_id=evidence_id,
                gate_id="no_unknown_or_future_support_refs",
                expected=sorted(applied_experience_ids),
                actual=evidence_id,
            )
        ]
    return []


def _validate_mutation_ref(
    mutation_id: str,
    *,
    request_id: str,
    applied_mutation_ids: set[str],
    all_mutations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if mutation_id not in all_mutations:
        return [
            make_failure(
                stage="scoring",
                type="unknown_evidence_reference",
                message=f"Mutation reference {mutation_id} is not known.",
                request_id=request_id,
                operation_id=mutation_id,
                gate_id="no_unknown_or_future_support_refs",
                expected="known public mutation ID",
                actual=mutation_id,
            )
        ]
    if mutation_id not in applied_mutation_ids:
        return [
            make_failure(
                stage="scoring",
                type="future_evidence_reference",
                message=f"Mutation reference {mutation_id} is after the request prefix.",
                request_id=request_id,
                operation_id=mutation_id,
                gate_id="no_unknown_or_future_support_refs",
                expected=sorted(applied_mutation_ids),
                actual=mutation_id,
            )
        ]
    return []


def _scope_failures(
    *,
    request_id: str,
    gate_id: str,
    metric_id: str,
    evidence_ids: list[str],
    request_scope: str,
    all_experiences: Mapping[str, Mapping[str, Any]],
    authorized_scope_ids: set[Any],
    failure_type: str,
    message_prefix: str,
) -> list[dict[str, Any]]:
    authorized = {str(scope) for scope in authorized_scope_ids if scope}
    if not authorized and request_scope:
        authorized = {request_scope}
    failures = []
    for evidence_id in sorted(set(evidence_ids)):
        experience = all_experiences.get(evidence_id)
        if not experience:
            continue
        scope_id = str(experience.get("scope_id") or "")
        if scope_id not in authorized:
            failures.append(
                make_failure(
                    stage="scoring",
                    type=failure_type,
                    message=f"{message_prefix} {evidence_id} is outside requested scope.",
                    request_id=request_id,
                    evidence_id=evidence_id,
                    gate_id=gate_id,
                    metric_id=metric_id,
                    expected=sorted(authorized),
                    actual=scope_id,
                )
            )
    return failures


def _authorized_scope_ids(
    gold: Mapping[str, Any],
    *,
    adapter_query: Mapping[str, Any],
    request: Mapping[str, Any],
) -> set[Any]:
    raw_scopes = gold.get("authorized_scope_ids") or [
        adapter_query.get("scope_id") or request.get("scope_id")
    ]
    return set(raw_scopes)


def _visible_exposure_ids(retrieval: Mapping[str, Any]) -> list[str]:
    evidence_ids: list[str] = []
    for item in retrieval.get("dropped") or []:
        if not isinstance(item, Mapping):
            continue
        for key in ("evidence_id", "support_experience_id", "source_experience_id"):
            if item.get(key):
                evidence_ids.append(str(item[key]))
        for key in ("evidence_ids", "support_experience_ids", "source_experience_ids"):
            evidence_ids.extend(str(value) for value in (item.get(key) or []))
    evidence_ids.extend(str(value) for value in (retrieval.get("visible_provenance_derived_evidence_ids") or []))
    return evidence_ids


def _requires_latency(manifest: Mapping[str, Any]) -> bool:
    return bool((manifest.get("capabilities") or {}).get("latency_reporting"))


def _has_latency_usage(retrieval: Mapping[str, Any]) -> bool:
    usage = retrieval.get("usage")
    if not isinstance(usage, Mapping):
        return False
    latency = usage.get("latency_ms")
    if not isinstance(latency, Mapping):
        return False
    return latency.get("retrieve") is not None and latency.get("total") is not None


def _expected_usage_failures(
    *,
    request_id: str,
    expected: Mapping[str, Any],
    retrieval: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not expected:
        return []
    usage = retrieval.get("usage") if isinstance(retrieval.get("usage"), Mapping) else {}
    counts = usage.get("counts") if isinstance(usage.get("counts"), Mapping) else {}
    failures = []

    expected_index_mode = expected.get("index_mode")
    if expected_index_mode is not None:
        actual_index_mode = counts.get("index_mode")
        if actual_index_mode != expected_index_mode:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="usage_expectation_mismatch",
                    message=f"Expected usage counts.index_mode={expected_index_mode!r}, got {actual_index_mode!r}.",
                    request_id=request_id,
                    gate_id="expected_usage_satisfied",
                    metric_id="expected_usage_satisfied",
                    expected={"counts.index_mode": expected_index_mode},
                    actual={"counts.index_mode": actual_index_mode},
                )
            )

    for key, minimum in expected.items():
        if not str(key).startswith("min_"):
            continue
        count_key = str(key)[4:]
        actual = counts.get(count_key)
        if not _meets_minimum(actual, minimum):
            failures.append(
                make_failure(
                    stage="scoring",
                    type="usage_expectation_mismatch",
                    message=f"Expected usage counts.{count_key}>={minimum!r}, got {actual!r}.",
                    request_id=request_id,
                    gate_id="expected_usage_satisfied",
                    metric_id="expected_usage_satisfied",
                    expected={f"counts.{count_key}": {"min": minimum}},
                    actual={f"counts.{count_key}": actual},
                )
            )
    return failures


def _expected_dropped_count_failures(
    *,
    request_id: str,
    expected: Mapping[str, Any],
    retrieval: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not expected:
        return []
    actual_counts = (
        retrieval.get("dropped_count_by_reason")
        if isinstance(retrieval.get("dropped_count_by_reason"), Mapping)
        else {}
    )
    failures = []
    for reason, minimum in sorted(expected.items(), key=lambda item: str(item[0])):
        reason_key = str(reason)
        actual = actual_counts.get(reason_key, 0)
        if not _meets_minimum(actual, minimum):
            failures.append(
                make_failure(
                    stage="scoring",
                    type="dropped_count_expectation_mismatch",
                    message=f"Expected dropped_count_by_reason.{reason_key}>={minimum!r}, got {actual!r}.",
                    request_id=request_id,
                    gate_id="expected_dropped_counts_satisfied",
                    metric_id="expected_dropped_counts_satisfied",
                    expected={f"dropped_count_by_reason.{reason_key}": {"min": minimum}},
                    actual={f"dropped_count_by_reason.{reason_key}": actual},
                )
            )
    return failures


def _expected_graph_verification_failures(
    *,
    request_id: str,
    expected: Mapping[str, Any],
    retrieval: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not expected:
        return []
    verification = (
        retrieval.get("derived_graph_index_verification")
        if isinstance(retrieval.get("derived_graph_index_verification"), Mapping)
        else {}
    )
    failures = []
    actual_ok = verification.get("ok")
    expected_ok = bool(expected.get("ok"))
    if "ok" in expected and (not isinstance(actual_ok, bool) or actual_ok != expected_ok):
        failures.append(
            make_failure(
                stage="scoring",
                type="derived_graph_index_expectation_mismatch",
                message=f"Expected derived_graph_index_verification.ok={expected_ok!r}, got {actual_ok!r}.",
                request_id=request_id,
                gate_id="expected_derived_graph_index_verification_satisfied",
                metric_id="expected_derived_graph_index_verification_satisfied",
                expected={"derived_graph_index_verification.ok": expected_ok},
                actual={"derived_graph_index_verification.ok": actual_ok},
            )
        )
    if "min_issue_count" in expected and not _meets_minimum(verification.get("issue_count"), expected.get("min_issue_count")):
        failures.append(
            make_failure(
                stage="scoring",
                type="derived_graph_index_expectation_mismatch",
                message=f"Expected derived_graph_index_verification.issue_count>={expected.get('min_issue_count')!r}, got {verification.get('issue_count')!r}.",
                request_id=request_id,
                gate_id="expected_derived_graph_index_verification_satisfied",
                metric_id="expected_derived_graph_index_verification_satisfied",
                expected={"derived_graph_index_verification.issue_count": {"min": expected.get("min_issue_count")}},
                actual={"derived_graph_index_verification.issue_count": verification.get("issue_count")},
            )
        )
    expected_issue_counts = (
        expected.get("issue_count_by_type")
        if isinstance(expected.get("issue_count_by_type"), Mapping)
        else {}
    )
    actual_issue_counts = (
        verification.get("issue_count_by_type")
        if isinstance(verification.get("issue_count_by_type"), Mapping)
        else {}
    )
    for issue_type, minimum in sorted(expected_issue_counts.items(), key=lambda item: str(item[0])):
        issue_key = str(issue_type)
        actual = actual_issue_counts.get(issue_key, 0)
        if not _meets_minimum(actual, minimum):
            failures.append(
                make_failure(
                    stage="scoring",
                    type="derived_graph_index_expectation_mismatch",
                    message=f"Expected derived_graph_index_verification.issue_count_by_type.{issue_key}>={minimum!r}, got {actual!r}.",
                    request_id=request_id,
                    gate_id="expected_derived_graph_index_verification_satisfied",
                    metric_id="expected_derived_graph_index_verification_satisfied",
                    expected={f"derived_graph_index_verification.issue_count_by_type.{issue_key}": {"min": minimum}},
                    actual={f"derived_graph_index_verification.issue_count_by_type.{issue_key}": actual},
                )
            )
    return failures


def _meets_minimum(actual: Any, minimum: Any) -> bool:
    try:
        return float(actual) >= float(minimum)
    except (TypeError, ValueError):
        return False


def _metrics(
    *,
    returned_count: int,
    k: int,
    item_relevance: list[int],
    support_ids: list[str],
    exposure_ids: list[str],
    relevant_ids: set[str],
    stale_ids: set[str],
    conflict_sets: list[Mapping[str, Any]],
    forbidden_ids: set[str],
    all_experiences: Mapping[str, Mapping[str, Any]],
    request_scope: str,
    authorized_scope_ids: set[Any],
    expected_abstention: Any,
    actual_abstention: bool,
    item_limit: int,
) -> dict[str, Any]:
    support_set = set(support_ids)
    denominator_k = max(1, k)
    recall = (len(support_set & relevant_ids) / len(relevant_ids)) if relevant_ids else None
    precision = sum(item_relevance[:k]) / denominator_k
    support_precision = len(support_set & relevant_ids) / max(1, len(support_set))
    mrr = 0.0
    for index, relevant in enumerate(item_relevance[:k], start=1):
        if relevant:
            mrr = 1.0 / index
            break
    ndcg = _ndcg(item_relevance[:k], k, ideal_relevant_count=min(k, len(relevant_ids)))
    authorized = {str(scope) for scope in authorized_scope_ids if scope}
    if not authorized and request_scope:
        authorized = {request_scope}
    unauthorized = [
        evidence_id
        for evidence_id in support_set
        if str((all_experiences.get(evidence_id) or {}).get("scope_id") or "") not in authorized
    ]
    exposure_set = set(exposure_ids)
    unauthorized_exposure = [
        evidence_id
        for evidence_id in exposure_set
        if str((all_experiences.get(evidence_id) or {}).get("scope_id") or "") not in authorized
    ]
    abstention_correct = None
    negative_space_correct = None
    false_abstention_rate = None
    missed_abstention_rate = None
    if expected_abstention is not None:
        abstention_correct = 1.0 if bool(expected_abstention) == actual_abstention else 0.0
        if bool(expected_abstention) and support_set:
            abstention_correct = 0.0
    if not relevant_ids:
        negative_space_correct = 1.0 if actual_abstention or not support_set else 0.0
    if expected_abstention is False or (expected_abstention is None and relevant_ids):
        false_abstention_rate = 1.0 if actual_abstention else 0.0
    if expected_abstention is True or (expected_abstention is None and not relevant_ids):
        missed_abstention_rate = 1.0 if (not actual_abstention or support_set) else 0.0
    contradiction_count = 0
    for conflict in conflict_sets:
        stale_present = set(str(value) for value in (conflict.get("stale_ids") or [])) & support_set
        fresh_present = set(str(value) for value in (conflict.get("fresh_ids") or [])) & support_set
        if stale_present and fresh_present:
            contradiction_count += 1
    return {
        "support_recall_at_k": recall,
        "recall_at_k": recall,
        "precision_at_k": precision,
        "support_precision_at_k": support_precision,
        "mrr_at_k": mrr,
        "ndcg_at_k": ndcg,
        "stale_as_fresh": len(support_set & stale_ids) / max(1, len(support_set)),
        "contradiction_as_fresh": contradiction_count / max(1, len(conflict_sets)),
        "cross_scope_leak_rate": len(unauthorized) / max(1, len(support_set)),
        "cross_scope_exposure_rate": len(unauthorized_exposure) / max(1, len(exposure_set)),
        "forbidden_retrieval_rate": len(support_set & forbidden_ids) / max(1, len(support_set)),
        "abstention_correct": abstention_correct,
        "negative_space_correct": negative_space_correct,
        "false_abstention_rate": false_abstention_rate,
        "missed_abstention_rate": missed_abstention_rate,
        "budget_violation": 1 if returned_count > item_limit else 0,
    }


def _ndcg(item_relevance: list[int], k: int, *, ideal_relevant_count: int) -> float:
    values = item_relevance + [0] * max(0, k - len(item_relevance))
    values = values[:k]
    dcg = sum(gain / math.log2(index + 1) for index, gain in enumerate(values, start=1))
    ideal = [1] * max(0, min(k, ideal_relevant_count))
    ideal.extend([0] * max(0, k - len(ideal)))
    idcg = sum(gain / math.log2(index + 1) for index, gain in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


def _status_reason(status: str, *, expected_failure_types: set[str]) -> str | None:
    if status == "expected_failure" and expected_failure_types:
        return "Observed failure types matched expected_failure_types."
    return None


def _threshold_failures(
    *,
    request: Mapping[str, Any],
    metrics: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> list[dict[str, Any]]:
    mode = str(request.get("mode") or "")
    cutoffs = ((profile.get("metric_cutoffs") or {}).get(mode) or {})
    failures = []
    mapping = {
        "recall_at_k_min": "recall_at_k",
        "mrr_at_k_min": "mrr_at_k",
        "ndcg_at_k_min": "ndcg_at_k",
    }
    for cutoff_key, metric_id in mapping.items():
        if cutoff_key not in cutoffs:
            continue
        observed = metrics.get(metric_id)
        required = cutoffs[cutoff_key]
        if observed is None or observed < required:
            failures.append(
                make_failure(
                    stage="scoring",
                    type="metric_hard_gate",
                    message=f"{metric_id}={observed} is below required {required}.",
                    request_id=str(request.get("request_id") or ""),
                    gate_id=f"{metric_id}_threshold",
                    metric_id=metric_id,
                    expected=required,
                    actual=observed,
                )
            )
    return failures


def _artifact_debug_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    retrieval_terms = metadata.get("retrieval_terms")
    if isinstance(retrieval_terms, (str, bytes)) or not isinstance(retrieval_terms, (list, tuple)):
        return {}
    terms = []
    seen: set[str] = set()
    for value in retrieval_terms:
        if not isinstance(value, str):
            continue
        text = " ".join(value.split())
        if not text or len(text) > 96:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(text)
        if len(terms) >= 32:
            break
    return {"retrieval_terms": terms} if terms else {}
