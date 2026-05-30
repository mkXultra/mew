import json

import pytest

from mew.memory_eval.adapters import DummyPassAdapter
from mew.memory_eval.hashing import canonical_json
from mew.memory_eval.synthetic_analogy import (
    EXACT_JSON_SCORING_ID,
    SyntheticAnalogyLeakageError,
    assert_no_scorer_field_leakage,
    count_mvp_whitespace_tokens,
    normalize_answer,
    phase0_artifact_hash,
    run_phase0_smoke,
    score_exact_json_answer,
    split_synthetic_analogy_fixture,
)


def _relation_lookup_fixture():
    return {
        "world_id": "world_relation_lookup_smoke",
        "hidden_world": {
            "entities": ["dax", "wug"],
            "relations": [{"subject": "dax", "relation": "nava", "object": "wug"}],
        },
        "public_experiences": [
            {
                "experience_id": "exp_relation_fact",
                "text": "dax is nava-related to wug.",
            }
        ],
        "tasks": [
            {
                "task_id": "task_relation_lookup",
                "family": "relation_lookup",
                "prompt": "In this local world, what is dax related to by nava?",
                "gold_answer": "wug",
                "oracle_context": ["dax is nava-related to wug."],
            }
        ],
    }


class CountingDummyPassAdapter(DummyPassAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.reset_calls = 0
        self.ingest_calls = 0
        self.retrieve_calls = 0

    def reset(self, run):
        self.reset_calls += 1
        return super().reset(run)

    def ingest(self, items):
        self.ingest_calls += 1
        return super().ingest(items)

    def retrieve(self, query):
        self.retrieve_calls += 1
        return super().retrieve(query)


def test_split_synthetic_analogy_fixture_hides_scorer_fields_and_uses_opaque_ids():
    views = split_synthetic_analogy_fixture(_relation_lookup_fixture())
    serialized = canonical_json(views.adapter_view)

    assert views.adapter_view["world_id"] == "world_000001"
    assert views.adapter_view["scope_id"] == "synthetic/world_000001"
    assert views.adapter_view["public_experiences"][0]["experience_id"] == "ex_000001"
    assert views.adapter_view["public_experiences"][0]["scope_id"] == "synthetic/world_000001"
    assert views.adapter_view["tasks"][0]["task_id"] == "rq_000001"
    assert views.adapter_view["tasks"][0]["scope_id"] == "synthetic/world_000001"
    assert "exp_relation_fact" not in serialized
    assert "world_relation_lookup_smoke" not in serialized
    assert "relation_lookup" not in serialized
    assert "smoke" not in serialized
    assert "gold_answer" not in serialized
    assert "oracle_context" not in serialized
    assert "hidden_world" not in serialized
    assert "family" not in serialized


@pytest.mark.parametrize("artifact_provider", ["harness_baseline_packet", "retrieve_packet"])
def test_phase0_smoke_loop_emits_json_report_for_three_conditions(tmp_path, artifact_provider):
    report_path = tmp_path / f"synthetic_analogy_smoke_{artifact_provider}.json"

    report = run_phase0_smoke(
        _relation_lookup_fixture(),
        DummyPassAdapter(),
        artifact_provider=artifact_provider,
        report_path=report_path,
    )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    rows_by_condition = {row["condition"]: row for row in report["per_task_rows"]}

    assert persisted == report
    assert report["state_isolation"] == "reset_per_condition_world"
    assert report["solver_profile"]["token_counter"] == "mvp_whitespace_v1"
    assert report["score_qualification"]["smoke_only"] is True
    assert report["score_qualification"]["reuse_allowed_for_mvp1_benchmark"] is False
    assert set(report["conditions"]) == {"memory_off", "memory_on", "oracle_context"}

    assert rows_by_condition["memory_off"]["scoring"]["score_method"] == EXACT_JSON_SCORING_ID
    assert rows_by_condition["memory_off"]["normalized_answer"] == "unknown"
    assert rows_by_condition["memory_off"]["per_task_success"] == 0
    assert rows_by_condition["memory_off"]["memory_artifact_tokens_used"] == 0
    assert rows_by_condition["memory_off"]["oracle_context_tokens_used"] == 0

    assert rows_by_condition["memory_on"]["normalized_answer"] == "wug"
    assert rows_by_condition["memory_on"]["per_task_success"] == 1
    assert rows_by_condition["memory_on"]["artifact_provider"] == artifact_provider
    assert rows_by_condition["memory_on"]["memory_calls_used"] == 1
    assert rows_by_condition["memory_on"]["evidence_ids"] == ["ex_000001"]
    assert rows_by_condition["memory_on"]["artifact_hash"].startswith("sha256:")

    expected_support_tokens = count_mvp_whitespace_tokens("dax is nava-related to wug.")
    assert rows_by_condition["memory_on"]["memory_artifact_tokens_used"] == expected_support_tokens
    assert rows_by_condition["oracle_context"]["normalized_answer"] == "wug"
    assert rows_by_condition["oracle_context"]["per_task_success"] == 1
    assert rows_by_condition["oracle_context"]["oracle_context_tokens_used"] == expected_support_tokens

    assert report["conditions"]["memory_off"]["task_count"] == 1
    assert report["conditions"]["memory_on"]["per_task_success"] == 1.0
    assert report["conditions"]["memory_on"]["budget_pass"] == 1.0
    assert report["conditions"]["memory_on"]["task_pass"] == 1.0
    assert report["conditions"]["memory_on"]["avg_memory_calls"] == 1.0
    assert report["conditions"]["memory_on"]["avg_memory_artifact_tokens"] == float(expected_support_tokens)
    assert report["conditions"]["oracle_context"]["avg_oracle_context_tokens"] == float(expected_support_tokens)
    assert report["conditions"]["memory_on"]["memory_lift"] == 1.0
    assert report["conditions"]["memory_on"]["oracle_gap"] == 0.0
    assert report["comparisons"]["memory_lift"] == 1.0
    assert report["comparisons"]["oracle_gap"] == 0.0


@pytest.mark.parametrize(
    ("payload", "field_name"),
    [
        ({"hidden_world": {"relations": []}}, "hidden_world"),
        ({"gold_answer": "wug"}, "gold_answer"),
        ({"oracle_context": ["dax is nava-related to wug."]}, "oracle_context"),
    ],
)
def test_leakage_gate_rejects_scorer_only_fields(payload, field_name):
    with pytest.raises(SyntheticAnalogyLeakageError) as exc_info:
        assert_no_scorer_field_leakage(payload, context="test_payload")

    failures = exc_info.value.failures
    assert {failure["type"] for failure in failures} == {"scorer_field_leakage"}
    assert failures[0]["actual"]["field"] == field_name


def test_exact_json_scoring_rejects_invalid_or_non_single_token_answers():
    invalid_json = score_exact_json_answer("{not-json}", "wug")
    multiple_tokens = score_exact_json_answer('{"answer":"two tokens"}', "wug")
    normalized = score_exact_json_answer('{"answer":"  WUG  "}', "wug")

    assert invalid_json["parse_ok"] is False
    assert invalid_json["error"] == "invalid_json"
    assert multiple_tokens["parse_ok"] is False
    assert multiple_tokens["error"] == "multiple_tokens"
    assert normalized["parse_ok"] is True
    assert normalized["normalized_answer"] == "wug"
    assert normalized["is_correct"] is True


def test_normalize_answer_accepts_mapping_and_rejects_missing_or_empty_answers():
    assert normalize_answer({"answer": "  WUG\t"}) == "wug"

    with pytest.raises(ValueError, match="missing_answer"):
        normalize_answer({"not_answer": "wug"})
    with pytest.raises(ValueError, match="empty_answer"):
        normalize_answer({"answer": "   "})


def test_phase0_artifact_hash_ignores_non_payload_fields():
    artifact = {
        "artifact_id": "artifact_world_task_memory_on",
        "task_id": "task_001",
        "world_id": "world_001",
        "condition": "memory_on",
        "artifact_provider": "harness_baseline_packet",
        "memory_calls_used": 1,
        "memory_artifact_tokens_used": 5,
        "artifact_text": "dax is nava-related to wug.",
        "evidence_ids": ["ex_000001"],
    }
    with_extra_fields = {
        **artifact,
        "normalized_answer": "wug",
        "per_task_success": 1,
        "budget_pass": True,
        "task_pass": 1,
        "score": {"is_correct": False},
        "answer": "wrong",
        "timestamp": "2026-05-30T00:00:00Z",
        "run_id": "run_ignored",
        "artifact_hash": "sha256:ignored",
    }

    assert phase0_artifact_hash(with_extra_fields) == phase0_artifact_hash(artifact)


def test_phase0_artifact_hash_is_canonical_but_preserves_array_order():
    artifact = {
        "artifact_provider": "harness_baseline_packet",
        "memory_artifact_tokens_used": 5,
        "world_id": "world_001",
        "evidence_ids": ["ex_000001", "ex_000002"],
        "artifact_text": "dax is nava-related to wug.\nzup is nava-related to mip.",
        "condition": "memory_on",
        "task_id": "task_001",
        "artifact_id": "artifact_world_task_memory_on",
        "memory_calls_used": 1,
    }
    same_payload_different_key_order = {
        "memory_calls_used": 1,
        "artifact_id": "artifact_world_task_memory_on",
        "task_id": "task_001",
        "condition": "memory_on",
        "artifact_text": "dax is nava-related to wug.\nzup is nava-related to mip.",
        "evidence_ids": ["ex_000001", "ex_000002"],
        "world_id": "world_001",
        "memory_artifact_tokens_used": 5,
        "artifact_provider": "harness_baseline_packet",
    }
    reversed_evidence_order = {
        **artifact,
        "evidence_ids": ["ex_000002", "ex_000001"],
    }

    assert phase0_artifact_hash(artifact) == phase0_artifact_hash(same_payload_different_key_order)
    assert phase0_artifact_hash(artifact) != phase0_artifact_hash(reversed_evidence_order)


def test_budget_failure_preserves_accuracy_but_fails_task_pass_and_pass_rate():
    report = run_phase0_smoke(
        _relation_lookup_fixture(),
        DummyPassAdapter(),
        budget_profile={"max_memory_calls": 0},
    )
    rows_by_condition = {row["condition"]: row for row in report["per_task_rows"]}

    assert rows_by_condition["memory_on"]["per_task_success"] == 1
    assert rows_by_condition["memory_on"]["budget_pass"] is False
    assert rows_by_condition["memory_on"]["task_pass"] == 0
    assert report["conditions"]["memory_on"]["accuracy"] == 1.0
    assert report["conditions"]["memory_on"]["pass_rate"] == 0.0
    assert report["conditions"]["memory_on"]["budget_pass"] == 0.0
    assert report["conditions"]["memory_on"]["budget_violation_rate"] == 1.0
    assert report["conditions"]["memory_on"]["memory_lift"] == 1.0
    assert report["conditions"]["memory_on"]["oracle_gap"] == 0.0


@pytest.mark.parametrize("artifact_provider", ["harness_baseline_packet", "retrieve_packet"])
def test_memory_call_accounting_excludes_reset_ingest_and_oracle_construction(artifact_provider):
    adapter = CountingDummyPassAdapter()

    report = run_phase0_smoke(
        _relation_lookup_fixture(),
        adapter,
        artifact_provider=artifact_provider,
    )
    rows_by_condition = {row["condition"]: row for row in report["per_task_rows"]}

    assert adapter.reset_calls == 3
    assert adapter.ingest_calls == 1
    assert adapter.retrieve_calls == 1
    assert rows_by_condition["memory_off"]["memory_calls_used"] == 0
    assert rows_by_condition["memory_on"]["memory_calls_used"] == 1
    assert rows_by_condition["oracle_context"]["memory_calls_used"] == 0
    assert report["conditions"]["memory_on"]["avg_memory_calls"] == 1.0


def test_token_split_totals_are_condition_specific():
    report = run_phase0_smoke(_relation_lookup_fixture(), DummyPassAdapter())
    rows_by_condition = {row["condition"]: row for row in report["per_task_rows"]}
    prompt_tokens = count_mvp_whitespace_tokens(
        "In this local world, what is dax related to by nava?"
    )
    support_tokens = count_mvp_whitespace_tokens("dax is nava-related to wug.")

    assert rows_by_condition["memory_off"]["task_prompt_tokens_used"] == prompt_tokens
    assert rows_by_condition["memory_off"]["memory_artifact_tokens_used"] == 0
    assert rows_by_condition["memory_off"]["oracle_context_tokens_used"] == 0
    assert rows_by_condition["memory_off"]["total_context_tokens_used"] == prompt_tokens

    assert rows_by_condition["memory_on"]["task_prompt_tokens_used"] == prompt_tokens
    assert rows_by_condition["memory_on"]["memory_artifact_tokens_used"] == support_tokens
    assert rows_by_condition["memory_on"]["oracle_context_tokens_used"] == 0
    assert rows_by_condition["memory_on"]["total_context_tokens_used"] == prompt_tokens + support_tokens

    assert rows_by_condition["oracle_context"]["task_prompt_tokens_used"] == prompt_tokens
    assert rows_by_condition["oracle_context"]["memory_artifact_tokens_used"] == 0
    assert rows_by_condition["oracle_context"]["oracle_context_tokens_used"] == support_tokens
    assert rows_by_condition["oracle_context"]["total_context_tokens_used"] == prompt_tokens + support_tokens


def test_string_oracle_context_normalizes_to_single_item_and_correct_token_count():
    fixture = _relation_lookup_fixture()
    fixture["tasks"][0]["oracle_context"] = "dax is nava-related to wug."

    views = split_synthetic_analogy_fixture(fixture)
    report = run_phase0_smoke(fixture, DummyPassAdapter())
    rows_by_condition = {row["condition"]: row for row in report["per_task_rows"]}

    assert views.scorer_view["tasks"][0]["oracle_context"] == ["dax is nava-related to wug."]
    assert rows_by_condition["oracle_context"]["evidence_items_used"] == 1
    assert rows_by_condition["oracle_context"]["oracle_context_tokens_used"] == count_mvp_whitespace_tokens(
        "dax is nava-related to wug."
    )


def test_invalid_oracle_context_shape_raises_clear_error():
    fixture = _relation_lookup_fixture()
    fixture["tasks"][0]["oracle_context"] = {"text": "dax is nava-related to wug."}

    with pytest.raises(ValueError, match="oracle_context must be None, a string, or a list/tuple of strings"):
        split_synthetic_analogy_fixture(fixture)
