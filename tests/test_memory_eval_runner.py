from pathlib import Path

import pytest

from mew.memory_eval.adapters import (
    CrossScopeExposureAdapter,
    CrossScopeLeakAdapter,
    DummyPassAdapter,
    DuplicateSupportAdapter,
    ForbiddenRetrievalAdapter,
    FutureSupportAdapter,
    InvalidRankingAdapter,
    MissingUsageAdapter,
    StaleAsFreshAdapter,
    SupportSourceMismatchAdapter,
    UnscorableEvidenceAdapter,
)
from mew.memory_eval.adapter_contract import default_usage
from mew.memory_eval.fixtures import load_fixture
from mew.memory_eval.runner import run_fixture


ROOT = Path(__file__).resolve().parents[1]
P0_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p0"
P1_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p1"


def test_dummy_happy_path_passes_with_denominator_inclusion():
    artifact = run_fixture(
        P0_FIXTURES / "dummy_happy_path.json",
        DummyPassAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["score_denominator_included"] is True
    assert request["gate_denominator_included"] is True
    assert request["metrics"]["recall_at_k"] == 1.0
    assert request["metrics"]["precision_at_k"] == 1.0
    assert request["metrics"]["mrr_at_k"] == 1.0
    assert request["retrieval"]["returned_evidence_order"][0]["support_experience_ids"] == ["exp_alpha"]
    assert request["retrieval"]["returned_evidence_order"][0]["scorable_support_ids"] == ["exp_alpha"]
    assert artifact["aggregate_metrics"]["status_counts"] == {"passed": 1}
    assert artifact["failures"] == []


@pytest.mark.parametrize(
    ("fixture_name", "adapter", "failure_type", "gate_id"),
    [
        ("broken_cross_scope_exposure.json", CrossScopeLeakAdapter(), "cross_scope_leak", "no_cross_scope_leak"),
        (
            "broken_cross_scope_exposure.json",
            CrossScopeExposureAdapter(),
            "cross_scope_leak",
            "no_cross_scope_exposure",
        ),
        (
            "broken_forbidden_retrieval.json",
            ForbiddenRetrievalAdapter(),
            "forbidden_retrieval",
            "no_forbidden_retrieval",
        ),
        (
            "broken_stale_as_fresh.json",
            StaleAsFreshAdapter(),
            "stale_as_fresh",
            "no_stale_as_fresh_when_strict",
        ),
        (
            "broken_invalid_support_reference.json",
            FutureSupportAdapter(),
            "future_evidence_reference",
            "no_unknown_or_future_support_refs",
        ),
        ("broken_invalid_ranking.json", InvalidRankingAdapter(), "invalid_ranking", "valid_rank_ordering"),
        (
            "broken_duplicate_support_reference.json",
            DuplicateSupportAdapter(),
            "duplicate_support_reference",
            "no_duplicate_support_reference",
        ),
        (
            "broken_unscorable_evidence.json",
            UnscorableEvidenceAdapter(),
            "unscorable_evidence",
            "required_support_mapping_present",
        ),
        (
            "broken_support_source_mismatch.json",
            SupportSourceMismatchAdapter(),
            "support_source_mismatch",
            "support_source_consistency",
        ),
        ("broken_duplicate_support_reference.json", MissingUsageAdapter(), "missing_usage", "required_usage_present"),
    ],
)
def test_broken_adapters_fail_intended_hard_gates(fixture_name, adapter, failure_type, gate_id):
    artifact = run_fixture(
        P0_FIXTURES / fixture_name,
        adapter,
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert failure_type in {failure["type"] for failure in request["failures"]}
    assert gate_id in {
        gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False
    }


def test_unsupported_capability_can_be_not_applicable_and_excluded_from_denominators():
    fixture = load_fixture(P0_FIXTURES / "broken_cross_scope_exposure.json")
    fixture["requests"][0]["on_unsupported"] = "not_applicable"

    class NoScopeAdapter(DummyPassAdapter):
        def manifest(self):
            manifest = super().manifest()
            manifest["capabilities"]["scope_enforcement"] = False
            return manifest

    artifact = run_fixture(
        fixture,
        NoScopeAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "not_applicable"
    assert request["score_denominator_included"] is False
    assert request["gate_denominator_included"] is False
    assert request["unsupported_capabilities"] == ["scope_enforcement"]
    assert artifact["aggregate_metrics"]["score_denominator_count"] == 0


def test_unsupported_capability_can_be_expected_failure_and_excluded_from_denominators():
    fixture = load_fixture(P0_FIXTURES / "broken_cross_scope_exposure.json")
    fixture["requests"][0]["on_unsupported"] = "expected_failure"

    class NoScopeAdapter(DummyPassAdapter):
        def manifest(self):
            manifest = super().manifest()
            manifest["capabilities"]["scope_enforcement"] = False
            return manifest

    artifact = run_fixture(
        fixture,
        NoScopeAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "expected_failure"
    assert request["score_denominator_included"] is False
    assert request["gate_denominator_included"] is False
    assert request["unsupported_capabilities"] == ["scope_enforcement"]
    assert {failure["type"] for failure in request["failures"]} == {"unsupported_capability"}
    assert artifact["aggregate_metrics"]["score_denominator_count"] == 0


def test_expected_failure_types_reclassifies_matching_observed_failures():
    fixture = load_fixture(P0_FIXTURES / "broken_duplicate_support_reference.json")
    fixture["requests"][0]["expected_failure_types"] = ["missing_usage"]

    artifact = run_fixture(
        fixture,
        MissingUsageAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "expected_failure"
    assert request["score_denominator_included"] is False
    assert request["gate_denominator_included"] is False
    assert request["status_reason"] == "Observed failure types matched expected_failure_types."
    assert {failure["type"] for failure in request["failures"]} == {"missing_usage"}


def test_authorized_scope_ids_drive_scope_metrics_not_request_scope_only():
    fixture = load_fixture(P0_FIXTURES / "broken_cross_scope_exposure.json")
    gold = fixture["requests"][0]["gold"]
    gold["authorized_scope_ids"] = ["tenant_a/user_a", "tenant_b/user_b"]
    gold["relevant_evidence_ids"] = ["exp_other"]

    artifact = run_fixture(
        fixture,
        CrossScopeLeakAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["metrics"]["cross_scope_leak_rate"] == 0
    assert request["metrics"]["cross_scope_exposure_rate"] == 0
    assert "cross_scope_leak" not in {failure["type"] for failure in request["failures"]}


def test_partial_retrieval_ndcg_uses_gold_ideal_capacity():
    fixture = load_fixture(P0_FIXTURES / "dummy_happy_path.json")
    fixture["requests"][0]["k"] = 2
    fixture["requests"][0]["budget"]["max_evidence_items"] = 2
    fixture["requests"][0]["gold"]["relevant_evidence_ids"] = ["exp_alpha", "exp_beta"]

    class FirstOnlyAdapter(DummyPassAdapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_ex_000001",
                        "evidence_id": "ex_000001",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000001"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        fixture,
        FirstOnlyAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    metrics = artifact["requests"][0]["metrics"]

    assert metrics["recall_at_k"] == 0.5
    assert metrics["ndcg_at_k"] < 1.0


def test_item_precision_stays_bounded_for_derived_memory_with_multiple_supports():
    fixture = load_fixture(P0_FIXTURES / "dummy_happy_path.json")
    fixture["requests"][0]["gold"]["relevant_evidence_ids"] = ["exp_alpha", "exp_beta"]

    class DerivedMultiSupportAdapter(DummyPassAdapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_derived",
                        "evidence_id": None,
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000001", "ex_000002"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        fixture,
        DerivedMultiSupportAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    metrics = artifact["requests"][0]["metrics"]

    assert metrics["precision_at_k"] == 1.0
    assert metrics["precision_at_k"] <= 1.0
    assert metrics["recall_at_k"] == 1.0


def test_metric_threshold_failures_are_reported_as_hard_gates():
    class WrongRelevantAdapter(DummyPassAdapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_ex_000002",
                        "evidence_id": "ex_000002",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000002"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P0_FIXTURES / "dummy_happy_path.json",
        WrongRelevantAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]
    failed_gates = {gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False}

    assert request["result_status"] == "failed"
    assert "metric_hard_gate" in {failure["type"] for failure in request["failures"]}
    assert "recall_at_k_threshold" in failed_gates
    assert "mrr_at_k_threshold" in failed_gates


def test_expected_usage_gold_gate_fails_when_graph_usage_is_not_reported():
    class GraphBypassAdapter(DummyPassAdapter):
        def manifest(self):
            manifest = super().manifest()
            manifest["adapter_id"] = "memory_eval_graph_bypass"
            manifest["capabilities"]["graph_expansion"] = True
            return manifest

        def retrieve(self, query):
            usage = default_usage(latency_ms=0.0)
            usage["counts"] = {
                "cards_scanned": 2,
                "cards_ranked": 1,
                "cards_returned": 1,
                "cards_dropped": 0,
                "graph_nodes_expanded": 0,
                "graph_edges_expanded": 0,
                "projection_chars": 16,
                "index_mode": "direct_scan",
            }
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_ex_000002",
                        "evidence_id": "ex_000002",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000002"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": usage,
                "failures": [],
            }

    artifact = run_fixture(
        P1_FIXTURES / "graph_expansion_basic.json",
        GraphBypassAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]
    failed_gates = {gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False}

    assert request["result_status"] == "failed"
    assert request["metrics"]["recall_at_k"] == 1.0
    assert request["metrics"]["expected_usage_satisfied"] == 0.0
    assert "usage_expectation_mismatch" in {failure["type"] for failure in request["failures"]}
    assert "expected_usage_satisfied" in failed_gates


def test_expected_dropped_count_gold_gate_fails_when_count_is_not_reported():
    fixture = load_fixture(P0_FIXTURES / "dummy_happy_path.json")
    fixture["requests"][0]["gold"]["expected_dropped_count_by_reason"] = {"privacy_block": 1}

    artifact = run_fixture(
        fixture,
        DummyPassAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]
    failed_gates = {gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False}

    assert request["result_status"] == "failed"
    assert request["metrics"]["expected_dropped_counts_satisfied"] == 0.0
    assert "dropped_count_expectation_mismatch" in {failure["type"] for failure in request["failures"]}
    assert "expected_dropped_counts_satisfied" in failed_gates


def test_expected_derived_graph_verification_gold_gate_fails_when_status_is_not_reported():
    fixture = load_fixture(P0_FIXTURES / "dummy_happy_path.json")
    fixture["requests"][0]["gold"]["expected_derived_graph_index_verification"] = {
        "ok": True,
        "min_issue_count": 0,
    }

    artifact = run_fixture(
        fixture,
        DummyPassAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]
    failed_gates = {gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False}

    assert request["result_status"] == "failed"
    assert request["metrics"]["expected_derived_graph_index_verification_satisfied"] == 0.0
    assert "derived_graph_index_expectation_mismatch" in {failure["type"] for failure in request["failures"]}
    assert "expected_derived_graph_index_verification_satisfied" in failed_gates


def test_adapter_returning_scorer_ids_directly_fails_opaque_ref_validation():
    class DirectScorerRefAdapter(DummyPassAdapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_exp_old",
                        "evidence_id": "exp_old",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["exp_old"],
                        "source_experience_ids": ["exp_old"],
                        "source_mutation_ids": ["mut_supersede"],
                        "support_mutation_ids": ["mut_supersede"],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [
                    {
                        "reason": "debug",
                        "evidence_ids": ["exp_old"],
                        "source_experience_id": "exp_old",
                        "source_experience_ids": ["exp_old"],
                    }
                ],
                "visible_provenance_derived_evidence_ids": ["exp_old"],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P0_FIXTURES / "broken_stale_as_fresh.json",
        DirectScorerRefAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "unknown_evidence_reference" in {failure["type"] for failure in request["failures"]}
    assert "no_unknown_or_future_support_refs" in {
        gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False
    }
    returned = request["retrieval"]["returned_evidence_order"][0]
    assert returned["support_experience_ids"] != ["exp_old"]
    assert returned["source_mutation_ids"] != ["mut_supersede"]


def test_dropped_source_refs_direct_scorer_ids_fail_opaque_validation():
    class DirectDroppedSourceRefAdapter(DummyPassAdapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_ex_000001",
                        "evidence_id": "ex_000001",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000001"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [
                    {
                        "reason": "debug",
                        "source_experience_id": "exp_alpha",
                        "source_experience_ids": ["exp_alpha"],
                    }
                ],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P0_FIXTURES / "dummy_happy_path.json",
        DirectDroppedSourceRefAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "unknown_evidence_reference" in {failure["type"] for failure in request["failures"]}
    assert "no_unknown_or_future_support_refs" in {
        gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False
    }


def test_dropped_source_refs_cross_scope_opaque_ids_fail_exposure_gate():
    class CrossScopeDroppedSourceRefAdapter(DummyPassAdapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_ex_000001",
                        "evidence_id": "ex_000001",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000001"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [
                    {
                        "reason": "debug",
                        "source_experience_id": "ex_000002",
                        "source_experience_ids": ["ex_000002"],
                    }
                ],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P0_FIXTURES / "broken_cross_scope_exposure.json",
        CrossScopeDroppedSourceRefAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "cross_scope_leak" in {failure["type"] for failure in request["failures"]}
    assert "no_cross_scope_exposure" in {
        gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False
    }
