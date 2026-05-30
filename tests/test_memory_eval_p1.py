from pathlib import Path

import pytest

from mew.memory_eval.adapter_contract import default_usage
from mew.memory_eval.adapters import ReferenceP1Adapter
from mew.memory_eval.fixtures import load_fixture
from mew.memory_eval.runner import run_fixture


ROOT = Path(__file__).resolve().parents[1]
P1_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p1"


P1_FIXTURE_NAMES = [
    "memory_off_no_prior_memory_basic.json",
    "memory_on_happy_path_basic.json",
    "retrieval_ranking_basic.json",
    "scope_isolation_basic.json",
    "stale_conflict_supersede_basic.json",
    "update_forget_basic.json",
    "abstention_no_memory_basic.json",
    "budget_limited_basic.json",
]

ANSWERABLE_ZERO_SUPPORT_FIXTURES = [
    "memory_on_happy_path_basic.json",
    "stale_conflict_supersede_basic.json",
    "update_forget_basic.json",
    "budget_limited_basic.json",
]


def _failure_types(request):
    return {failure["type"] for failure in request["failures"]}


def _failed_gate_ids(request):
    return {gate["gate_id"] for gate in request["hard_gates"] if gate["passed"] is False}


@pytest.mark.parametrize("fixture_name", P1_FIXTURE_NAMES)
def test_reference_adapter_passes_initial_p1_fixtures(fixture_name):
    artifact = run_fixture(
        P1_FIXTURES / fixture_name,
        ReferenceP1Adapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert artifact["phase"] == "P1"
    assert request["result_status"] == "passed"
    assert request["score_denominator_included"] is True
    assert request["gate_denominator_included"] is True
    assert request["failures"] == []
    assert request["retrieval"]["hash_usage_fields"]["latency_source"] == "harness_measured"
    assert request["retrieval"]["hash_usage_fields"]["cost_methodology"] == "not_reported"
    assert request["retrieval"]["hash_usage_fields"]["token_methodology"] == "not_reported"


def test_p1_retrieval_metrics_are_support_based_and_item_level():
    artifact = run_fixture(
        P1_FIXTURES / "retrieval_ranking_basic.json",
        ReferenceP1Adapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    metrics = artifact["requests"][0]["metrics"]

    assert metrics["support_recall_at_k"] == 1.0
    assert metrics["recall_at_k"] == 1.0
    assert metrics["precision_at_k"] == pytest.approx(1 / 3)
    assert metrics["support_precision_at_k"] == pytest.approx(1 / 3)
    assert metrics["mrr_at_k"] == 1.0
    assert metrics["ndcg_at_k"] == 1.0


def test_p1_budget_wrong_in_budget_item_fails_relevant_top_one_requirement():
    class WrongTopOneAdapter(ReferenceP1Adapter):
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
        P1_FIXTURES / "budget_limited_basic.json",
        WrongTopOneAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert request["metrics"]["recall_at_k"] == 0.0
    assert request["metrics"]["mrr_at_k"] == 0.0
    assert "missing_relevant_support" in _failure_types(request)
    assert "relevant_support_present" in _failed_gate_ids(request)
    assert "recall_at_k_threshold" in _failed_gate_ids(request)
    assert "mrr_at_k_threshold" in _failed_gate_ids(request)


@pytest.mark.parametrize("fixture_name", ANSWERABLE_ZERO_SUPPORT_FIXTURES)
def test_p1_answerable_zero_support_false_non_abstention_fails(fixture_name):
    class EmptyButNotAbstainedAdapter(ReferenceP1Adapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P1_FIXTURES / fixture_name,
        EmptyButNotAbstainedAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert request["metrics"]["recall_at_k"] == 0.0
    assert "missing_relevant_support" in _failure_types(request)
    assert "relevant_support_present" in _failed_gate_ids(request)


@pytest.mark.parametrize(
    "fixture_name",
    ["memory_off_no_prior_memory_basic.json", "abstention_no_memory_basic.json"],
)
def test_p1_true_negative_space_still_passes_with_real_abstention(fixture_name):
    artifact = run_fixture(
        P1_FIXTURES / fixture_name,
        ReferenceP1Adapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["retrieval"]["abstained"] is True
    assert request["metrics"]["negative_space_correct"] == 1.0
    assert request["metrics"]["missed_abstention_rate"] == 0.0


def test_p1_scores_derived_memory_with_support_experience_ids():
    class DerivedAdapter(ReferenceP1Adapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "summary_ex_000001",
                        "evidence_id": None,
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
        P1_FIXTURES / "memory_on_happy_path_basic.json",
        DerivedAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    returned = request["retrieval"]["returned_evidence_order"][0]
    assert returned["evidence_ref"] == "summary_ex_000001"
    assert returned["evidence_id"] is None
    assert returned["scorable_support_ids"] == ["exp_green_tea"]
    assert request["metrics"]["support_recall_at_k"] == 1.0


def test_p1_accepts_legacy_source_experience_ids_as_current_support():
    class LegacySourceAdapter(ReferenceP1Adapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "legacy_ex_000001",
                        "evidence_id": None,
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "source_experience_ids": ["ex_000001"],
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
        P1_FIXTURES / "memory_on_happy_path_basic.json",
        LegacySourceAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "passed"
    assert request["retrieval"]["returned_evidence_order"][0]["scorable_support_ids"] == ["exp_green_tea"]


def test_p1_support_source_mismatch_fails_hard_gate():
    class MismatchAdapter(ReferenceP1Adapter):
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
                        "source_experience_ids": ["ex_000002"],
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
        P1_FIXTURES / "retrieval_ranking_basic.json",
        MismatchAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "support_source_mismatch" in _failure_types(request)
    assert "support_source_consistency" in _failed_gate_ids(request)


def test_p1_future_support_and_mutation_refs_are_rejected_by_request_prefix():
    fixture = {
        "schema_version": "memory_eval_fixture.v1",
        "fixture_id": "p1_request_checkpoint_future_refs",
        "fixture_version": "1.0.0",
        "fixture_family": "memory_on_happy_path",
        "phase": "P1",
        "evaluation_time": "2026-05-21T00:00:00Z",
        "experiences": [
            {
                "experience_id": "exp_ready_code",
                "scope_id": "tenant_a/user_a",
                "session_id": "session_170",
                "turn_id": "turn_001",
                "event_time": "2026-01-19T09:00:00Z",
                "ingest_order": 1,
                "actor_id": "user_a",
                "payload": {
                    "mime_type": "text/plain",
                    "text": "Mira uses code Linden for release notes.",
                },
                "visibility": {
                    "allowed_scope_ids": ["tenant_a/user_a"],
                    "retrievable": True,
                },
            },
            {
                "experience_id": "exp_later_code",
                "scope_id": "tenant_a/user_a",
                "session_id": "session_170",
                "turn_id": "turn_002",
                "event_time": "2026-01-19T09:05:00Z",
                "ingest_order": 2,
                "actor_id": "user_a",
                "payload": {
                    "mime_type": "text/plain",
                    "text": "Mira uses code Maple for release notes.",
                },
                "visibility": {
                    "allowed_scope_ids": ["tenant_a/user_a"],
                    "retrievable": True,
                },
            },
        ],
        "mutations": [
            {
                "op_id": "mut_later_code",
                "mutation_type": "supersede",
                "target_experience_id": "exp_ready_code",
                "replacement_experience_id": "exp_later_code",
                "effective_time": "2026-01-19T09:06:00Z",
                "reason": "newer code",
            }
        ],
        "requests": [
            {
                "request_id": "req_checkpoint",
                "mode": "memory_on_happy_path",
                "scope_id": "tenant_a/user_a",
                "query_time": "2026-01-19T09:03:00Z",
                "query": {
                    "text": "Which code does Mira use for release notes?",
                    "intent": "preference_lookup",
                },
                "k": 2,
                "filters": {
                    "valid_at": "2026-01-19T09:03:00Z",
                    "allowed_states": ["active"],
                },
                "budget": {
                    "max_evidence_items": 2,
                    "max_latency_ms": 200,
                    "max_cost_units": None,
                },
                "requires_capabilities": ["retrieve"],
                "on_unsupported": "hard_failure",
                "gold": {
                    "relevant_evidence_ids": ["exp_ready_code"],
                    "must_not_return_evidence_ids": [],
                    "stale_evidence_ids": [],
                    "expected_abstention": False,
                },
            }
        ],
        "operation_sequence": [
            {"type": "ingest", "experience_id": "exp_ready_code", "ingest_order": 1},
            {"type": "request", "request_id": "req_checkpoint", "after_ingest_order": 1},
            {"type": "ingest", "experience_id": "exp_later_code", "ingest_order": 2},
            {"type": "mutate", "op_id": "mut_later_code", "ingest_order": 3},
        ],
    }

    class FutureRefAdapter(ReferenceP1Adapter):
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
                        "source_mutation_ids": ["mu_000001"],
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
        FutureRefAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "future_evidence_reference" in _failure_types(request)
    assert "no_unknown_or_future_support_refs" in _failed_gate_ids(request)


def test_p1_scope_isolation_leak_fails_exposure_gate():
    class CrossScopeAdapter(ReferenceP1Adapter):
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
                        "scope_id": "tenant_b/user_b",
                    }
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P1_FIXTURES / "scope_isolation_basic.json",
        CrossScopeAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "cross_scope_leak" in _failure_types(request)
    assert request["metrics"]["cross_scope_leak_rate"] == 1.0
    assert "no_cross_scope_leak" in _failed_gate_ids(request)


def test_p1_stale_conflict_returns_old_and_new_as_hard_failure():
    class StaleConflictAdapter(ReferenceP1Adapter):
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
                    },
                    {
                        "evidence_ref": "mem_ex_000001",
                        "evidence_id": "ex_000001",
                        "rank": 2,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000001"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    },
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P1_FIXTURES / "stale_conflict_supersede_basic.json",
        StaleConflictAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert {"stale_as_fresh", "contradiction_as_fresh"} <= _failure_types(request)
    assert request["metrics"]["contradiction_as_fresh"] == 1.0
    assert "no_stale_as_fresh_when_strict" in _failed_gate_ids(request)
    assert "no_contradiction_as_fresh_when_strict" in _failed_gate_ids(request)


def test_p1_forget_fixture_rejects_forgotten_forbidden_support():
    class ForgottenAdapter(ReferenceP1Adapter):
        def retrieve(self, query):
            return {
                "request_id": query.get("request_id"),
                "ranked_evidence": [
                    {
                        "evidence_ref": "mem_ex_000003",
                        "evidence_id": "ex_000003",
                        "rank": 1,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000003"],
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
        P1_FIXTURES / "update_forget_basic.json",
        ForgottenAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert {"forbidden_retrieval", "stale_as_fresh"} <= _failure_types(request)
    assert "no_forbidden_retrieval" in _failed_gate_ids(request)


def test_p1_stale_conflict_without_supersede_is_not_applicable():
    fixture = load_fixture(P1_FIXTURES / "stale_conflict_supersede_basic.json")

    class NoSupersedeAdapter(ReferenceP1Adapter):
        def manifest(self):
            manifest = super().manifest()
            manifest["capabilities"]["supersede"] = False
            return manifest

    artifact = run_fixture(
        fixture,
        NoSupersedeAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "not_applicable"
    assert request["score_denominator_included"] is False
    assert request["gate_denominator_included"] is False
    assert artifact["aggregate_metrics"]["score_denominator_count"] == 0


def test_p1_abstention_fixture_rejects_returned_support():
    class MissedAbstentionAdapter(ReferenceP1Adapter):
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
        P1_FIXTURES / "abstention_no_memory_basic.json",
        MissedAbstentionAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "abstention_mismatch" in _failure_types(request)
    assert request["metrics"]["abstention_correct"] == 0.0
    assert request["metrics"]["negative_space_correct"] == 0.0
    assert request["metrics"]["missed_abstention_rate"] == 1.0


def test_p1_budget_fixture_rejects_over_budget_items():
    class OverBudgetAdapter(ReferenceP1Adapter):
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
                    },
                    {
                        "evidence_ref": "mem_ex_000002",
                        "evidence_id": "ex_000002",
                        "rank": 2,
                        "score": None,
                        "score_type": "none",
                        "support_experience_ids": ["ex_000002"],
                        "source_mutation_ids": [],
                        "state": "active",
                        "scope_id": query.get("scope_id"),
                    },
                ],
                "abstained": False,
                "abstained_reason": None,
                "dropped": [],
                "usage": default_usage(latency_ms=0.0),
                "failures": [],
            }

    artifact = run_fixture(
        P1_FIXTURES / "budget_limited_basic.json",
        OverBudgetAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "failed"
    assert "budget_violation" in _failure_types(request)
    assert request["metrics"]["budget_violation"] == 1
    assert "item_budget_respected" in _failed_gate_ids(request)


def test_p1_update_forget_requires_capability_without_counting_as_pass():
    fixture = load_fixture(P1_FIXTURES / "update_forget_basic.json")

    class NoForgetAdapter(ReferenceP1Adapter):
        def manifest(self):
            manifest = super().manifest()
            manifest["capabilities"]["forget"] = False
            return manifest

    artifact = run_fixture(
        fixture,
        NoForgetAdapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )
    request = artifact["requests"][0]

    assert request["result_status"] == "not_applicable"
    assert request["score_denominator_included"] is False
    assert request["gate_denominator_included"] is False
    assert artifact["aggregate_metrics"]["score_denominator_count"] == 0


def test_p1_memory_off_mode_is_separate_in_aggregate_metadata():
    artifact = run_fixture(
        P1_FIXTURES / "memory_off_no_prior_memory_basic.json",
        ReferenceP1Adapter(),
        run_id="run_fixed",
        created_at="2026-05-21T00:00:00Z",
    )

    assert artifact["requests"][0]["mode"] == "memory_off"
    assert artifact["aggregate_metrics"]["status_counts_by_mode"]["memory_off"] == {"passed": 1}
    assert "memory_off" in artifact["aggregate_metrics"]["metric_averages_by_mode"]
