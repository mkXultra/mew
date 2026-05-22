from __future__ import annotations

import json
from pathlib import Path

from mew.memory_eval.fixtures import load_fixture
from mew.memory_eval_live_runner import (
    GRAPH_ON_FIXTURE_SUFFIX,
    LIVE_FIXTURE_SUFFIX,
    NORMAL_9_SUITE,
    add_seed_lifecycle,
    build_parser,
    compact_suite_summary,
    enable_graph_retrieval,
    exit_code_for_artifact,
    exit_code_for_suite,
    resolve_output_path,
    run_live_typed_cards_suite,
    summarize_artifact,
    suite_fixture_paths,
)


ROOT = Path(__file__).resolve().parents[1]
P1_FIXTURES = ROOT / "fixtures" / "memory_eval" / "p1"


def test_add_seed_lifecycle_inserts_public_seed_after_each_ingest() -> None:
    source = load_fixture(P1_FIXTURES / "memory_on_happy_path_basic.json")
    rewritten = add_seed_lifecycle(source)

    assert source["fixture_id"] == "memory_on_happy_path_basic"
    assert rewritten["fixture_id"] == f"memory_on_happy_path_basic{LIVE_FIXTURE_SUFFIX}"
    assert rewritten["mutations"][0] == {
        "op_id": "setup_seed_000001",
        "mutation_type": "seed_eval",
        "target_experience_id": "exp_green_tea",
        "effective_time": "2026-05-21T00:00:00Z",
        "reason": "typed-card live eval setup",
    }
    assert rewritten["operation_sequence"] == [
        {"type": "ingest", "experience_id": "exp_green_tea", "ingest_order": 1},
        {"type": "mutate", "op_id": "setup_seed_000001", "ingest_order": 1},
        {"type": "request", "request_id": "req_memory_on_primary", "after_ingest_order": 1},
    ]


def test_add_seed_lifecycle_preserves_existing_mutations_after_setup() -> None:
    source = load_fixture(P1_FIXTURES / "update_forget_basic.json")
    rewritten = add_seed_lifecycle(source)

    setup_ids = [
        mutation["op_id"]
        for mutation in rewritten["mutations"]
        if mutation["mutation_type"] == "seed_eval"
    ]

    assert setup_ids == ["setup_seed_000001", "setup_seed_000002", "setup_seed_000003"]
    assert rewritten["mutations"][3]["op_id"] == "mut_update_folder"
    assert json.dumps(rewritten["operation_sequence"]).index("setup_seed_000001") < json.dumps(
        rewritten["operation_sequence"]
    ).index("mut_update_folder")


def test_enable_graph_retrieval_marks_every_request() -> None:
    source = load_fixture(P1_FIXTURES / "memory_on_happy_path_basic.json")
    rewritten = enable_graph_retrieval(source, graph_max_depth=1, graph_max_items=7)

    assert rewritten["fixture_id"] == f"memory_on_happy_path_basic{GRAPH_ON_FIXTURE_SUFFIX}"
    request = rewritten["requests"][0]
    assert request["filters"]["valid_at"] == "2026-03-01T12:00:00Z"
    assert request["filters"]["expand_graph"] is True
    assert request["filters"]["graph_max_depth"] == 1
    assert request["filters"]["graph_max_items"] == 7
    assert "gold" in source["requests"][0]


def test_live_runner_parser_defaults_to_home_codex_auth() -> None:
    args = build_parser().parse_args(["fixtures/memory_eval/p1/memory_on_happy_path_basic.json"])

    assert args.model == "gpt-5.5"
    assert args.backend == "codex"
    assert args.call_interface == "call_model_structured_json"
    assert str(args.auth_json).endswith(".codex/auth.json")
    assert args.seed_lifecycle is True
    assert args.expand_graph is False


def test_live_runner_parser_accepts_graph_controls() -> None:
    args = build_parser().parse_args(
        [
            "fixtures/memory_eval/p1/memory_on_happy_path_basic.json",
            "--expand-graph",
            "--graph-max-depth",
            "1",
            "--graph-max-items",
            "9",
        ]
    )

    assert args.expand_graph is True
    assert args.graph_max_depth == 1
    assert args.graph_max_items == 9


def test_live_runner_parser_accepts_normal_suite_without_fixture() -> None:
    args = build_parser().parse_args(["--suite", "normal-9"])

    assert args.fixture is None
    assert args.suite == NORMAL_9_SUITE


def test_live_runner_parser_accepts_all_normal_alias_without_fixture() -> None:
    args = build_parser().parse_args(["--all-normal"])

    assert args.fixture is None
    assert args.suite == NORMAL_9_SUITE


def test_normal_9_suite_fixture_order_is_stable() -> None:
    fixtures = suite_fixture_paths(NORMAL_9_SUITE)

    assert [path.name for path in fixtures] == [
        "dummy_happy_path.json",
        "memory_off_no_prior_memory_basic.json",
        "budget_limited_basic.json",
        "scope_isolation_basic.json",
        "memory_on_happy_path_basic.json",
        "retrieval_ranking_basic.json",
        "abstention_no_memory_basic.json",
        "update_forget_basic.json",
        "stale_conflict_supersede_basic.json",
    ]


def test_resolve_output_path_uses_run_id_when_output_is_omitted(tmp_path: Path) -> None:
    output = resolve_output_path(None, output_dir=tmp_path, run_id="live run/one")

    assert output == tmp_path / "live_run_one.json"


def test_summarize_artifact_keeps_live_eval_output_small(tmp_path: Path) -> None:
    artifact = {
        "run_id": "run_live",
        "fixture": {"fixture_id": "fx"},
        "adapter": {
            "adapter_id": "mew_typed_cards_memory_eval",
            "external_model_ids": ["codex:gpt-5.5"],
        },
        "aggregate_metrics": {"status_counts": {"passed": 1}},
        "hard_gates": [{"gate_id": "valid_rank_ordering", "passed": True}],
        "failures": [],
        "requests": [
            {
                "fixture_request_id": "req_a",
                "result_status": "passed",
                "metrics": {"recall_at_k": 1.0},
                "failures": [],
            }
        ],
    }

    summary = summarize_artifact(artifact, tmp_path / "artifact.json")

    assert summary == {
        "run_id": "run_live",
        "output": str(tmp_path / "artifact.json"),
        "fixture_id": "fx",
        "adapter_id": "mew_typed_cards_memory_eval",
        "external_model_ids": ["codex:gpt-5.5"],
        "status_counts": {"passed": 1},
        "hard_gates": [{"gate_id": "valid_rank_ordering", "passed": True}],
        "failure_count": 0,
        "failure_types": [],
        "requests": [
            {
                "request_id": "req_a",
                "status": "passed",
                "metrics": {"recall_at_k": 1.0},
                "failure_types": [],
            }
        ],
    }


def test_exit_code_for_artifact_fails_on_scoring_failure() -> None:
    failed = {"aggregate_metrics": {"status_counts": {"failed": 1}}, "failures": []}

    assert exit_code_for_artifact(failed) == 1
    assert exit_code_for_artifact(failed, allow_failures=True) == 0


def test_compact_suite_summary_omits_verbose_request_details(tmp_path: Path) -> None:
    summary = {
        "suite": NORMAL_9_SUITE,
        "run_id": "suite_run",
        "output_dir": str(tmp_path),
        "backend": "codex",
        "model": "gpt-5.5",
        "fixture_count": 1,
        "failed_count": 0,
        "status_counts": {"passed": 1},
        "failed_fixtures": [],
        "fixtures": [
            {
                "source_fixture": "fixtures/memory_eval/p0/dummy_happy_path.json",
                "fixture_id": "dummy_happy_path",
                "status_counts": {"passed": 1},
                "failure_count": 0,
                "output": str(tmp_path / "dummy.json"),
                "requests": [{"metrics": {"recall_at_k": 1.0}}],
                "hard_gates": [{"gate_id": "valid_rank_ordering", "passed": True}],
            }
        ],
    }

    compact = compact_suite_summary(summary, tmp_path / "summary.json")

    assert compact["output"] == str(tmp_path / "summary.json")
    assert compact["expand_graph"] is False
    assert compact["fixtures"] == [
        {
            "source_fixture": "fixtures/memory_eval/p0/dummy_happy_path.json",
            "fixture_id": "dummy_happy_path",
            "status_counts": {"passed": 1},
            "failure_count": 0,
            "output": str(tmp_path / "dummy.json"),
        }
    ]


def test_run_live_typed_cards_suite_uses_injected_runner_and_writes_summary(tmp_path: Path) -> None:
    calls = []

    def fake_run_fixture(fixture_path, **kwargs):
        calls.append((Path(fixture_path), kwargs))
        status = "passed"
        failures = []
        if Path(fixture_path).name == "budget_limited_basic.json":
            failures = [{"type": "missing_relevant_support"}]
            status = "failed"
        artifact = {
            "run_id": kwargs["run_id"],
            "fixture": {"fixture_id": Path(fixture_path).stem},
            "adapter": {
                "adapter_id": "mew_typed_cards_memory_eval",
                "external_model_ids": ["codex:gpt-5.5"],
            },
            "aggregate_metrics": {"status_counts": {status: 1}},
            "hard_gates": [],
            "failures": failures,
            "requests": [],
        }
        return artifact, Path(kwargs["output_dir"]) / f"{kwargs['run_id']}.json"

    summary, output = run_live_typed_cards_suite(
        NORMAL_9_SUITE,
        auth_json="/tmp/auth.json",
        run_id="suite_run",
        output_dir=tmp_path,
        expand_graph=True,
        graph_max_items=9,
        run_fixture_fn=fake_run_fixture,
    )

    assert output == tmp_path / "suite_run" / "summary.json"
    assert output.exists()
    assert summary["suite"] == NORMAL_9_SUITE
    assert summary["fixture_count"] == 9
    assert summary["failed_count"] == 1
    assert summary["status_counts"] == {"passed": 8, "failed": 1}
    assert summary["failed_fixtures"][0]["source_fixture"].endswith("budget_limited_basic.json")
    assert calls[0][1]["auth_json"] == "/tmp/auth.json"
    assert calls[0][1]["fixture_ordinal"] == 1
    assert calls[0][1]["expand_graph"] is True
    assert calls[0][1]["graph_max_items"] == 9
    assert calls[-1][1]["fixture_ordinal"] == 9
    assert summary["expand_graph"] is True


def test_exit_code_for_suite_fails_when_any_fixture_failed() -> None:
    failed = {"failed_count": 1}

    assert exit_code_for_suite(failed) == 1
    assert exit_code_for_suite(failed, allow_failures=True) == 0
