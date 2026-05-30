import json

import pytest

from mew.memory_eval.adapters import DummyPassAdapter
from mew.memory_eval.hashing import canonical_json
from mew.memory_eval.synthetic_analogy import (
    DEFAULT_MVP1_PACK_SEED,
    EXACT_JSON_SCORING_ID,
    MVP1_ALLOWED_FAMILIES,
    MVP1_PACK_TASK_COUNT,
    PHASE4_CONDITION_COMPARISON_SCHEMA,
    SYNTHETIC_ANALOGY_PROFILE_NAMES,
    SYNTHETIC_ANALOGY_PROFILE_PACK20,
    SYNTHETIC_ANALOGY_PROFILE_SMOKE,
    SyntheticAnalogyLeakageError,
    assert_no_scorer_field_leakage,
    count_mvp_whitespace_tokens,
    find_answer_token_leakage_tasks,
    format_synthetic_analogy_profile_summary,
    generate_mvp1_pack,
    is_ascii_lowercase_single_token,
    main as synthetic_analogy_main,
    mvp1_task_determinism_signature,
    normalize_answer,
    phase0_artifact_hash,
    run_mvp1_pack20,
    run_phase0_smoke,
    run_synthetic_analogy_profile,
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
    assert report["score_qualification"]["benchmark_quality"] is False
    assert isinstance(report["score_qualification"]["benchmark_quality"], bool)
    assert report["score_qualification"]["benchmark_quality_level"] is None
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
    expected_prompt_tokens = count_mvp_whitespace_tokens(
        "In this local world, what is dax related to by nava?"
    )
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
    assert report["condition_comparison"]["schema"] == PHASE4_CONDITION_COMPARISON_SCHEMA
    assert report["condition_comparison"]["purpose"] == "display_only_same_task_set_condition_comparison"
    assert report["condition_comparison"]["task_set"] == {
        "same_task_set_across_conditions": True,
        "task_count": 1,
        "task_ids": ["task_relation_lookup"],
        "task_ids_by_condition": {
            "memory_off": ["task_relation_lookup"],
            "memory_on": ["task_relation_lookup"],
            "oracle_context": ["task_relation_lookup"],
        },
        "diagnostic_task_ids_excluded": [],
    }
    assert report["condition_comparison"]["budget_limits"] == {
        "max_memory_calls": 1,
        "max_total_context_tokens": 600,
        "max_evidence_items": 8,
    }
    comparison_rows = {
        row["condition"]: row for row in report["condition_comparison"]["condition_rows"]
    }
    assert comparison_rows["memory_off"]["accuracy"] == 0.0
    assert comparison_rows["memory_on"]["accuracy"] == 1.0
    assert comparison_rows["oracle_context"]["accuracy"] == 1.0
    assert comparison_rows["memory_on"]["budget_usage"]["budget_pass_rate"] == 1.0
    assert comparison_rows["memory_on"]["budget_usage"]["avg_memory_calls"] == 1.0
    assert comparison_rows["memory_on"]["budget_usage"]["avg_total_context_tokens"] == float(
        expected_prompt_tokens + expected_support_tokens
    )
    assert report["condition_comparison"]["comparisons"] == {
        "memory_lift": 1.0,
        "oracle_gap": 0.0,
    }
    assert "Smoke score is not benchmark-quality MVP-1 memory scoring." in report["known_limitations"]
    assert "No long-term retention; state is reset inside the local harness." in report["known_limitations"]
    assert "No structured claim scoring; exact JSON single-token scoring only." in report["known_limitations"]
    assert (
        "No terminal bench, full agent behavior, behavior_eval, or network dependency."
        in report["known_limitations"]
    )
    assert expected_prompt_tokens > 0


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


def test_diagnostic_task_rows_are_retained_but_excluded_from_condition_aggregates():
    fixture = _relation_lookup_fixture()
    fixture["public_experiences"].append(
        {
            "experience_id": "exp_relation_fact_2",
            "text": "zup is mavo-related to mip.",
        }
    )
    fixture["tasks"][0]["diagnostic"] = True
    fixture["tasks"][0]["diagnostics"] = {"forced_diagnostic": True}
    fixture["tasks"][0]["gold_answer"] = "nix"
    fixture["tasks"].append(
        {
            "task_id": "task_relation_lookup_normal",
            "family": "relation_lookup",
            "prompt": "In this local world, what is zup related to by mavo?",
            "gold_answer": "mip",
            "oracle_context": ["zup is mavo-related to mip."],
        }
    )

    report = run_phase0_smoke(fixture, DummyPassAdapter())
    diagnostic_rows = [row for row in report["per_task_rows"] if row["diagnostic"]]
    normal_rows = [row for row in report["per_task_rows"] if not row["diagnostic"]]
    diagnostic_by_condition = {row["condition"]: row for row in diagnostic_rows}
    normal_by_condition = {row["condition"]: row for row in normal_rows}

    assert len(report["per_task_rows"]) == 6
    assert len(diagnostic_rows) == 3
    assert len(normal_rows) == 3
    assert {row["task_id"] for row in diagnostic_rows} == {"task_relation_lookup"}
    assert {row["condition"] for row in diagnostic_rows} == {"memory_off", "memory_on", "oracle_context"}
    assert all(row["diagnostics"] == {"forced_diagnostic": True} for row in diagnostic_rows)
    assert diagnostic_by_condition["memory_on"]["per_task_success"] == 0
    assert diagnostic_by_condition["memory_on"]["task_pass"] == 0
    assert diagnostic_by_condition["oracle_context"]["per_task_success"] == 0
    assert diagnostic_by_condition["oracle_context"]["task_pass"] == 0
    assert normal_by_condition["memory_on"]["per_task_success"] == 1
    assert normal_by_condition["memory_on"]["task_pass"] == 1
    assert normal_by_condition["oracle_context"]["per_task_success"] == 1
    assert normal_by_condition["oracle_context"]["task_pass"] == 1
    assert report["conditions"]["memory_off"]["task_count"] == 1
    assert report["conditions"]["memory_on"]["task_count"] == 1
    assert report["conditions"]["oracle_context"]["task_count"] == 1
    assert report["conditions"]["memory_on"]["accuracy"] == 1.0
    assert report["conditions"]["memory_on"]["pass_rate"] == 1.0
    assert report["conditions"]["oracle_context"]["accuracy"] == 1.0
    assert report["conditions"]["oracle_context"]["pass_rate"] == 1.0


def test_mvp1_pack20_generation_is_deterministic_and_family_limited():
    first = generate_mvp1_pack(DEFAULT_MVP1_PACK_SEED)
    second = generate_mvp1_pack(DEFAULT_MVP1_PACK_SEED)

    assert first["pack_metadata"]["fixture_materialization"] == "runtime_generation_only"
    assert len(first["tasks"]) == MVP1_PACK_TASK_COUNT
    assert len(first["public_experiences"]) == MVP1_PACK_TASK_COUNT
    assert mvp1_task_determinism_signature(first) == mvp1_task_determinism_signature(second)
    assert {task["family"] for task in first["tasks"]} == set(MVP1_ALLOWED_FAMILIES)
    assert {task["family"] for task in first["tasks"]} == {
        "relation_lookup",
        "analogy_completion",
        "rule_application",
    }

    signature = mvp1_task_determinism_signature(first)
    assert all(item["oracle_support_hash"].startswith("sha256:") for item in signature)
    assert [item["task_id"] for item in signature] == [task["task_id"] for task in first["tasks"]]


def test_mvp1_pack20_answers_are_single_ascii_tokens_without_prompt_leakage():
    fixture = generate_mvp1_pack()

    assert find_answer_token_leakage_tasks(fixture) == []
    for task in fixture["tasks"]:
        assert is_ascii_lowercase_single_token(task["gold_answer"])
        assert task["diagnostic"] is False
        assert task["diagnostics"]["answer_token_leakage"] is False
        assert task["gold_answer"] not in task["prompt"].lower().split()


def test_mvp1_pack20_run_report_includes_phase2_metrics_and_diagnostics(tmp_path):
    report_path = tmp_path / "mvp1_pack20_report.json"

    report = run_mvp1_pack20(DummyPassAdapter(), report_path=report_path)

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted == report
    assert report["phase"] == "P2"
    assert report["pack_generation"]["pack_id"] == "synthetic_analogy_mvp1_pack20"
    assert report["pack_generation"]["seed"] == DEFAULT_MVP1_PACK_SEED
    assert report["pack_generation"]["task_count"] == MVP1_PACK_TASK_COUNT
    assert report["pack_generation"]["fixture_materialization"] == "runtime_generation_only"
    assert report["score_qualification"]["benchmark_quality"] is True
    assert isinstance(report["score_qualification"]["benchmark_quality"], bool)
    assert report["score_qualification"]["benchmark_quality_level"] == "mvp1_minimal_fixed_solver"
    assert set(report["conditions"]) == {"memory_off", "memory_on", "oracle_context"}
    assert len(report["per_task_rows"]) == MVP1_PACK_TASK_COUNT * 3

    for condition in ("memory_off", "memory_on", "oracle_context"):
        summary = report["conditions"][condition]
        assert summary["task_count"] == MVP1_PACK_TASK_COUNT
        assert "avg_memory_calls" in summary
        assert "avg_total_context_tokens" in summary
        assert "budget_violation_rate" in summary
        assert "memory_lift" in summary
        assert "oracle_gap" in summary

    assert report["conditions"]["memory_off"]["accuracy"] == 0.0
    assert report["conditions"]["memory_on"]["accuracy"] == 1.0
    assert report["conditions"]["oracle_context"]["accuracy"] == 1.0
    assert report["comparisons"]["memory_lift"] == 1.0
    assert report["comparisons"]["oracle_gap"] == 0.0
    assert report["condition_comparison"]["schema"] == PHASE4_CONDITION_COMPARISON_SCHEMA
    assert report["condition_comparison"]["task_set"]["same_task_set_across_conditions"] is True
    assert report["condition_comparison"]["task_set"]["task_count"] == MVP1_PACK_TASK_COUNT
    assert len(report["condition_comparison"]["condition_rows"]) == 3
    comparison_rows = {
        row["condition"]: row for row in report["condition_comparison"]["condition_rows"]
    }
    assert comparison_rows["memory_off"]["accuracy"] == 0.0
    assert comparison_rows["memory_on"]["pass_rate"] == 1.0
    assert comparison_rows["oracle_context"]["budget_usage"]["budget_pass_rate"] == 1.0
    assert "No long-term retention; state is reset inside the local harness." in report["known_limitations"]
    assert "No structured claim scoring; exact JSON single-token scoring only." in report["known_limitations"]
    assert (
        "No terminal bench, full agent behavior, behavior_eval, or network dependency."
        in report["known_limitations"]
    )
    assert report["diagnostics"]["answer_token_leakage"]["suspicious_task_ids"] == []
    assert report["diagnostics"]["answer_token_leakage"]["normal_aggregate_excludes_suspicious"] is True
    assert report["diagnostics"]["memory_off_floor"]["status"] == "diagnostic_only"
    assert report["diagnostics"]["memory_off_floor"]["accuracy"] == 0.0


def test_synthetic_analogy_profile_smoke_writes_report_and_summary(tmp_path):
    report_path = tmp_path / "smoke_profile_report.json"

    result = run_synthetic_analogy_profile(
        SYNTHETIC_ANALOGY_PROFILE_SMOKE,
        output_path=report_path,
    )

    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted == result.report
    assert result.output_path == str(report_path)
    assert result.report["profile"] == SYNTHETIC_ANALOGY_PROFILE_SMOKE
    assert result.report["phase"] == "P0"
    assert result.report["profile_phase"] == "P3_profile_command_manual_gate"
    assert result.report["profile_execution"] == {
        "local_manual_default": True,
        "ci_default_integration": False,
        "terminal_bench_integration": False,
        "behavior_eval_integration": False,
        "live_model_execution": False,
    }
    assert result.report["profile_report_hash"].startswith("sha256:")
    assert result.report["conditions"]["memory_on"]["accuracy"] == 1.0
    assert "JSON report: " + str(report_path) in result.summary
    assert "JSON artifact is the source of record." in result.summary
    assert "Score qualification: smoke-only; benchmark_quality=false" in result.summary
    assert "not MVP-1 benchmark-quality" in result.summary
    assert "Task set: same_task_set=true, task_count=1" in result.summary
    assert "- memory_off: accuracy=0.000, pass_rate=0.000" in result.summary
    assert "- memory_on: accuracy=1.000, pass_rate=1.000" in result.summary
    assert "- oracle_context: accuracy=1.000, pass_rate=1.000" in result.summary
    assert "budget=pass=1.000" in result.summary
    assert "memory_lift=1.000" in result.summary
    assert "No long-term retention" in result.summary
    assert "No structured claim scoring" in result.summary
    assert "full agent behavior" in result.summary
    assert "Manual/local only" in result.summary


def test_synthetic_analogy_profile_pack20_report_is_deterministic(tmp_path):
    first_path = tmp_path / "pack20_profile_first.json"
    second_path = tmp_path / "pack20_profile_second.json"

    first = run_synthetic_analogy_profile(
        SYNTHETIC_ANALOGY_PROFILE_PACK20,
        output_path=first_path,
    )
    second = run_synthetic_analogy_profile(
        SYNTHETIC_ANALOGY_PROFILE_PACK20,
        output_path=second_path,
    )

    assert first.report == second.report
    assert json.loads(first_path.read_text(encoding="utf-8")) == first.report
    assert json.loads(second_path.read_text(encoding="utf-8")) == second.report
    assert first.report["profile"] == SYNTHETIC_ANALOGY_PROFILE_PACK20
    assert first.report["phase"] == "P2"
    assert first.report["pack_generation"]["task_count"] == MVP1_PACK_TASK_COUNT
    assert first.report["profile_execution"]["ci_default_integration"] is False
    assert first.report["profile_execution"]["terminal_bench_integration"] is False
    assert first.report["profile_execution"]["behavior_eval_integration"] is False
    assert first.report["conditions"]["memory_off"]["accuracy"] == 0.0
    assert first.report["conditions"]["memory_on"]["accuracy"] == 1.0
    assert first.report["comparisons"]["memory_lift"] == 1.0
    assert first.report["condition_comparison"]["task_set"]["task_count"] == MVP1_PACK_TASK_COUNT


def test_synthetic_analogy_profile_main_writes_json_and_prints_summary(tmp_path, capsys):
    report_path = tmp_path / "pack20_profile_cli.json"

    exit_code = synthetic_analogy_main(
        [
            "--profile",
            SYNTHETIC_ANALOGY_PROFILE_PACK20,
            "--output",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["profile"] == SYNTHETIC_ANALOGY_PROFILE_PACK20
    assert "Synthetic analogy profile synthetic-analogy-mvp-pack20 completed (P2)." in captured.out
    assert "JSON report: " + str(report_path) in captured.out
    assert "Score qualification: benchmark_quality=true, level=mvp1_minimal_fixed_solver" in captured.out
    assert "same_task_set=true, task_count=20" in captured.out
    assert "No structured claim scoring" in captured.out
    assert "memory_lift=1.000" in captured.out


def test_synthetic_analogy_profile_rejects_unknown_profile(tmp_path, capsys):
    assert SYNTHETIC_ANALOGY_PROFILE_NAMES == (
        "synthetic-analogy-mvp-smoke",
        "synthetic-analogy-mvp-pack20",
    )

    with pytest.raises(ValueError, match="unknown synthetic analogy profile"):
        run_synthetic_analogy_profile(
            "synthetic-analogy-missing",
            output_path=tmp_path / "missing.json",
        )

    exit_code = synthetic_analogy_main(
        [
            "--profile",
            "synthetic-analogy-missing",
            "--output",
            str(tmp_path / "missing_cli.json"),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "unknown synthetic analogy profile" in captured.err


def test_synthetic_analogy_profile_help_lists_profiles_and_usage(capsys):
    with pytest.raises(SystemExit) as exc_info:
        synthetic_analogy_main(["--help"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "Run local synthetic analogy MVP profiles." in captured.out
    assert "Profiles:" in captured.out
    assert SYNTHETIC_ANALOGY_PROFILE_SMOKE in captured.out
    assert SYNTHETIC_ANALOGY_PROFILE_PACK20 in captured.out
    assert "Default adapter: DummyPassAdapter" in captured.out
    assert "real memory" in captured.out
    assert "subsystem is a separate adapter-integration step" in captured.out


def test_synthetic_analogy_profile_summary_can_be_formatted_without_output_path(tmp_path):
    result = run_synthetic_analogy_profile(
        SYNTHETIC_ANALOGY_PROFILE_SMOKE,
        output_path=tmp_path / "smoke_profile_report.json",
    )

    summary = format_synthetic_analogy_profile_summary(result.report)

    assert "JSON report:" not in summary
    assert "synthetic-analogy-mvp-smoke completed (P0)" in summary
    assert "oracle_gap=0.000" in summary
