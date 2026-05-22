from __future__ import annotations

import json
from pathlib import Path

from mew.memory_eval.fixtures import load_fixture
from mew.memory_eval_live_runner import (
    LIVE_FIXTURE_SUFFIX,
    add_seed_lifecycle,
    build_parser,
    exit_code_for_artifact,
    resolve_output_path,
    summarize_artifact,
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


def test_live_runner_parser_defaults_to_home_codex_auth() -> None:
    args = build_parser().parse_args(["fixtures/memory_eval/p1/memory_on_happy_path_basic.json"])

    assert args.model == "gpt-5.5"
    assert args.backend == "codex"
    assert args.call_interface == "call_model_structured_json"
    assert str(args.auth_json).endswith(".codex/auth.json")
    assert args.seed_lifecycle is True


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
