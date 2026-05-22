import json
from copy import deepcopy
from pathlib import Path

from mew.memory_eval.fixtures import split_fixture
from mew.memory_eval.hashing import canonical_json
from mew.memory_eval.membench import (
    audit_mteb_source_manifest,
    build_ephemeral_fixtures_from_dry_run,
    build_typed_cards_ephemeral_fixtures_from_dry_run,
    convert_mteb_qrels_dry_run,
    main as membench_main,
    validate_mteb_qrels_dry_run,
)


ROOT = Path(__file__).resolve().parents[1]
MEMORY_EVAL_FIXTURES = ROOT / "fixtures" / "memory_eval"


def test_mteb_source_audit_records_external_no_vendor_manifest(tmp_path):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [{"_id": "doc-1", "text": "Aki keeps green tea nearby."}],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"_id": "query-1", "text": "Which drink does Aki keep?"}],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-1\tdoc-1\t1\n", encoding="utf-8"
    )

    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision="0123456789abcdef",
        source_subset="single_hop",
        declared_license="MIT",
        license_source="synthetic test audit",
        citation_targets=["mteb/MemBench dataset card", "MTEB"],
    )

    assert manifest["source_mode"] == "external_huggingface"
    assert manifest["source_dataset"] == "mteb/MemBench"
    assert manifest["source_revision_status"] == "pinned"
    assert manifest["source_subset"] == "single_hop"
    assert manifest["local_cache_only"] is True
    assert manifest["generated_fixture_commit_policy"] == "no_vendor_by_default"
    assert manifest["declared_license"] == "MIT"
    assert manifest["license_certainty"] == "declared_unverified"
    assert manifest["citation_required"] is True
    assert manifest["redistribution_status"] == "private_only"
    assert {item["path"] for item in manifest["raw_file_hashes"]} == {
        "corpus.jsonl",
        "queries.jsonl",
        "qrels.tsv",
    }
    assert all(
        item["sha256"].startswith("sha256:") for item in manifest["raw_file_hashes"]
    )


def test_mteb_qrels_dry_run_maps_docs_through_corpus_manifest_and_hides_gold(tmp_path):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {
                "_id": "doc-green",
                "title": "Tea note",
                "text": "Aki keeps green tea nearby.",
            },
            {
                "_id": "doc-window",
                "text": "Aki reserves the window seat for train rides.",
            },
        ],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [
            {
                "_id": "query-window",
                "text": "Which seat does Aki reserve for train rides?",
                "choices": ["aisle", "window"],
                "answer": "window",
                "ground_truth": "B",
            }
        ],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-window\tdoc-window\t1\n",
        encoding="utf-8",
    )
    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision="0123456789abcdef",
        source_subset="single_hop",
        declared_license="MIT",
        license_source="synthetic test audit",
    )

    report = convert_mteb_qrels_dry_run(tmp_path, source_manifest=manifest)

    assert report["seed"] == 12345
    assert report["candidate_counts"]["selected_fixture_previews"] == 1
    assert report["candidate_counts"]["skipped_examples"] == 0
    assert report["adapter_view_check_summary"] == {
        "passed": True,
        "fixture_count": 1,
        "failure_count": 0,
    }
    preview = report["fixture_previews"][0]
    assert preview["adapter_fixture_id"] == "fx_000001"
    scorer_request = preview["scorer_view"]["requests"][0]
    assert scorer_request["gold"]["relevant_evidence_ids"] == ["exp_src_000002"]
    assert (
        scorer_request["gold"]["source_qrels"][0]["experience_id"] == "exp_src_000002"
    )
    assert scorer_request["gold"]["source_qrels"][0]["source_locator_hash"].startswith(
        "sha256:"
    )
    assert preview["hash_sensitivity"]["public_hash_unchanged"] is True
    assert preview["hash_sensitivity"]["gold_hash_changed"] is True
    assert preview["hash_sensitivity"]["full_hash_changed"] is True
    assert {
        item["experience_id"] for item in preview["scorer_view"]["experiences"]
    } == {
        "exp_src_000001",
        "exp_src_000002",
    }

    adapter_json = canonical_json(preview["adapter_view"])
    assert "source_benchmark" not in adapter_json
    assert "source_qrels" not in adapter_json
    assert "source_locator" not in adapter_json
    assert "doc-window" not in adapter_json
    assert "qrels.tsv" not in adapter_json
    assert "choices" not in adapter_json
    assert "answer" not in adapter_json
    assert "ground_truth" not in adapter_json
    assert "target_step_id" not in adapter_json
    assert "mteb/MemBench" not in adapter_json
    assert preview["adapter_view"]["experiences"][0]["experience_id"] == "ex_000001"


def test_mteb_dry_run_validation_uses_ephemeral_fixtures_without_pack_writes(
    tmp_path,
):
    fixture_tree_before = _fixture_tree_snapshot()
    report = _validation_ready_dry_run_report(tmp_path)

    fixtures = build_ephemeral_fixtures_from_dry_run(report)
    assert len(fixtures) == 1
    assert {item["experience_id"] for item in fixtures[0]["experiences"]} == {
        "exp_src_000001",
        "exp_src_000002",
    }

    preview = report["fixture_previews"][0]
    views = split_fixture(fixtures[0])
    assert views.fixture_public_hash == preview["fixture_public_hash"]
    assert views.fixture_gold_hash == preview["fixture_gold_hash"]
    assert views.fixture_full_hash == preview["fixture_full_hash"]

    validation = validate_mteb_qrels_dry_run(report)

    assert validation["validation_status"] == "passed"
    assert validation["ephemeral_fixture_policy"]["storage"] == "in_memory_only"
    assert validation["ephemeral_fixture_policy"]["writes_fixture_pack"] is False
    assert validation["selected_fixture_count"] == 1
    assert validation["reference_adapter"]["result_summary"]["passed"] is True
    reference = validation["reference_adapter"]["results"][0]
    assert reference["result_status"] == "passed"
    assert reference["hash_match"] == {
        "fixture_public_hash_matches_preview": True,
        "fixture_gold_hash_matches_preview": True,
        "fixture_full_hash_matches_preview": True,
    }
    assert reference["adapter_view_leakage_failure_count"] == 0
    assert (
        reference["fixture_hashes"]["fixture_public_hash"]
        == preview["fixture_public_hash"]
    )

    controls = {
        item["control_id"]: item for item in validation["negative_controls"]["results"]
    }
    assert {
        "duplicate_support",
        "missing_usage",
        "support_source_mismatch",
        "unscorable_evidence",
    } <= set(controls)
    assert all(
        item["negative_control_status"] == "passed" for item in controls.values()
    )
    assert (
        "no_duplicate_support_reference"
        in controls["duplicate_support"]["observed_failed_gate_ids"]
    )
    assert (
        "required_support_mapping_present"
        in controls["unscorable_evidence"]["observed_failed_gate_ids"]
    )
    assert (
        "required_usage_present"
        in controls["missing_usage"]["observed_failed_gate_ids"]
    )
    assert (
        "support_source_consistency"
        in controls["support_source_mismatch"]["observed_failed_gate_ids"]
    )
    assert {
        item["control_id"] for item in validation["negative_controls"]["not_run"]
    } >= {"cross_scope_exposure", "future_support", "stale_as_fresh"}

    adapter_json = canonical_json(views.adapter_view)
    assert "source_benchmark" not in adapter_json
    assert "source_qrels" not in adapter_json
    assert "source_locator" not in adapter_json
    assert "doc-green" not in adapter_json
    assert "qrels.tsv" not in adapter_json
    assert "target_step_id" not in adapter_json
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_mteb_dry_run_validation_can_include_typed_cards_deterministic_replay(
    tmp_path,
):
    fixture_tree_before = _fixture_tree_snapshot()
    report = _validation_ready_dry_run_report(tmp_path)

    typed_fixtures = build_typed_cards_ephemeral_fixtures_from_dry_run(report)
    assert len(typed_fixtures) == 1
    typed_fixture = typed_fixtures[0]
    assert [item["mutation_type"] for item in typed_fixture["mutations"]] == [
        "seed_eval",
        "seed_eval",
    ]
    assert [
        item["type"] for item in typed_fixture["operation_sequence"][:4]
    ] == ["ingest", "mutate", "ingest", "mutate"]
    typed_views = split_fixture(typed_fixture)
    typed_adapter_json = canonical_json(typed_views.adapter_view)
    assert "source_benchmark" not in typed_adapter_json
    assert "source_qrels" not in typed_adapter_json
    assert "source_locator" not in typed_adapter_json
    assert "doc-green" not in typed_adapter_json
    assert "qrels.tsv" not in typed_adapter_json
    assert "target_step_id" not in typed_adapter_json

    validation = validate_mteb_qrels_dry_run(report, include_typed_cards=True)

    assert validation["validation_status"] == "passed"
    assert validation["typed_cards_adapter"]["run"] is True
    assert validation["typed_cards_adapter"]["extractor_mode"] == "deterministic_replay"
    assert validation["typed_cards_adapter"]["live_model_extraction"] is False
    assert validation["typed_cards_adapter"]["result_summary"]["passed"] is True
    typed = validation["typed_cards_adapter"]["results"][0]
    assert typed["result_status"] == "passed"
    assert typed["request_statuses"] == ["passed"]
    assert typed["failed_gate_ids"] == []
    assert typed["failure_types"] == []
    assert typed["source_hash_match"] == {
        "fixture_public_hash_matches_preview": True,
        "fixture_gold_hash_matches_preview": True,
        "fixture_full_hash_matches_preview": True,
    }
    assert typed["typed_cards_setup_mutation_count"] == 2
    assert typed["typed_cards_adapter_view_leakage_failure_count"] == 0
    assert typed["artifact_hashes"]["deterministic_result_hash"].startswith("sha256:")
    assert typed["artifact_hashes"]["retrieval_result_hash"].startswith("sha256:")
    assert typed["typed_cards_fixture_hashes"]["fixture_public_hash"].startswith(
        "sha256:"
    )
    assert (
        typed["typed_cards_fixture_hashes"]["fixture_public_hash"]
        != report["fixture_previews"][0]["fixture_public_hash"]
    )
    assert typed["usage_summary"]["run_usage_reported"] is True
    assert typed["usage_summary"]["count_totals"]["cards_returned"] >= 1
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_mteb_validate_dry_run_report_cli_emits_stdout_json(tmp_path, capsys):
    report = _validation_ready_dry_run_report(tmp_path)
    report_path = tmp_path / "dry_run.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

    assert membench_main(["validate-dry-run-report", str(report_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "mew_membench_dry_run_validation.v1"
    assert output["validation_status"] == "passed"
    assert (
        output["ephemeral_fixture_policy"]["generated_fixture_pack_committed"] is False
    )
    assert output["typed_cards_adapter"]["run"] is False


def test_mteb_validate_dry_run_report_cli_can_include_typed_cards(
    tmp_path, capsys
):
    report = _validation_ready_dry_run_report(tmp_path)
    report_path = tmp_path / "dry_run_typed.json"
    report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

    assert (
        membench_main(
            [
                "validate-dry-run-report",
                str(report_path),
                "--include-typed-cards",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["validation_status"] == "passed"
    assert output["typed_cards_adapter"]["run"] is True
    assert output["typed_cards_adapter"]["result_summary"]["passed"] is True
    assert output["typed_cards_adapter"]["results"][0]["result_status"] == "passed"


def test_mteb_validate_dry_run_report_infers_non_default_seed(tmp_path, capsys):
    report = _validation_ready_dry_run_report(tmp_path, seed=6789)
    report_path = tmp_path / "dry_run_non_default_seed.json"
    saved_report = deepcopy(report)
    saved_report.pop("seed")
    report_path.write_text(json.dumps(saved_report, sort_keys=True), encoding="utf-8")

    assert report["seed"] == 6789
    assert report["fixture_previews"][0]["adapter_view"]["seed"] == 6789
    assert membench_main(["validate-dry-run-report", str(report_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    reference = output["reference_adapter"]["results"][0]
    assert output["seed"] == 6789
    assert output["validation_status"] == "passed"
    assert reference["hash_match"] == {
        "fixture_public_hash_matches_preview": True,
        "fixture_gold_hash_matches_preview": True,
        "fixture_full_hash_matches_preview": True,
    }
    assert (
        reference["fixture_hashes"]["fixture_public_hash"]
        == report["fixture_previews"][0]["fixture_public_hash"]
    )


def test_mteb_qrels_dry_run_rejects_missing_qrel_doc(tmp_path):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [{"_id": "doc-1", "text": "Aki keeps green tea nearby."}],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"_id": "query-1", "text": "Which drink does Aki keep?"}],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-1\tdoc-missing\t1\n",
        encoding="utf-8",
    )

    report = convert_mteb_qrels_dry_run(
        tmp_path,
        source_manifest=audit_mteb_source_manifest(
            tmp_path, source_revision="0123456789abcdef"
        ),
    )

    assert report["qrel_mapping"]["success_count"] == 0
    assert report["skipped_examples"][0]["reason"] == "missing_qrel_doc"
    assert report["skipped_examples"][0]["doc_id_hashes"][0].startswith("sha256:")


def test_mteb_qrels_dry_run_rejects_ambiguous_duplicate_qrel_doc(tmp_path):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {"_id": "doc-dup", "text": "First duplicate source text."},
            {"_id": "doc-dup", "text": "Second duplicate source text."},
        ],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"_id": "query-1", "text": "What duplicate text matters?"}],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-1\tdoc-dup\t1\n", encoding="utf-8"
    )

    report = convert_mteb_qrels_dry_run(
        tmp_path,
        source_manifest=audit_mteb_source_manifest(
            tmp_path, source_revision="0123456789abcdef"
        ),
    )

    assert report["qrel_mapping"]["success_count"] == 0
    assert report["candidate_counts"]["duplicate_doc_ids"] == 1
    assert report["skipped_examples"][0]["reason"] == "ambiguous_qrel_doc"


def test_source_benchmark_is_scorer_only_and_changes_gold_hash_only():
    fixture = {
        "schema_version": "memory_eval_fixture.v1",
        "fixture_id": "synthetic_source_hash",
        "fixture_version": "1.0.0",
        "fixture_family": "synthetic",
        "phase": "P1",
        "evaluation_time": "2026-05-22T00:00:00Z",
        "source_benchmark": {"benchmark_id": "membench", "source_revision": "rev-a"},
        "experiences": [
            {
                "experience_id": "exp_src_000001",
                "scope_id": "tenant/user",
                "session_id": "session_1",
                "turn_id": "turn_1",
                "event_time": "2026-05-21T00:00:00Z",
                "ingest_order": 1,
                "actor_id": "observer",
                "payload": {
                    "mime_type": "text/plain",
                    "text": "Aki keeps green tea nearby.",
                },
                "visibility": {
                    "allowed_scope_ids": ["tenant/user"],
                    "retrievable": True,
                },
                "metadata": {"source_kind": "synthetic_memory_observation"},
            }
        ],
        "mutations": [],
        "requests": [
            {
                "request_id": "req_1",
                "mode": "membench_mteb_qrels_support_retrieval",
                "scope_id": "tenant/user",
                "query_time": "2026-05-22T00:00:00Z",
                "query": {
                    "text": "Which drink does Aki keep?",
                    "intent": "memory_lookup",
                },
                "k": 1,
                "filters": {
                    "valid_at": "2026-05-22T00:00:00Z",
                    "allowed_states": ["active"],
                },
                "budget": {
                    "max_evidence_items": 1,
                    "max_latency_ms": 500,
                    "max_cost_units": None,
                },
                "requires_capabilities": ["retrieve"],
                "on_unsupported": "hard_failure",
                "gold": {
                    "relevant_evidence_ids": ["exp_src_000001"],
                    "source_qrels": [{"experience_id": "exp_src_000001", "score": 1.0}],
                },
            }
        ],
        "operation_sequence": [
            {"type": "ingest", "experience_id": "exp_src_000001", "ingest_order": 1},
            {"type": "request", "request_id": "req_1", "after_ingest_order": 1},
        ],
    }

    changed = deepcopy(fixture)
    changed["source_benchmark"]["source_revision"] = "rev-b"
    first = split_fixture(fixture)
    second = split_fixture(changed)

    assert "source_benchmark" not in canonical_json(first.adapter_view)
    assert first.scorer_view["source_benchmark"]["source_revision"] == "rev-a"
    assert first.fixture_public_hash == second.fixture_public_hash
    assert first.fixture_gold_hash != second.fixture_gold_hash
    assert first.fixture_full_hash != second.fixture_full_hash


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _fixture_tree_snapshot():
    return sorted(
        path.relative_to(MEMORY_EVAL_FIXTURES)
        for path in MEMORY_EVAL_FIXTURES.rglob("*")
        if path.is_file()
    )


def _validation_ready_dry_run_report(tmp_path, *, seed=12345):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {
                "_id": "doc-green",
                "text": "Aki stores the green tea tin beside the kettle.",
            },
            {
                "_id": "doc-bike",
                "text": "Rin parks the blue bicycle near the station gate.",
            },
        ],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [
            {
                "_id": "query-green",
                "text": "Where does Aki store the green tea tin?",
                "choices": ["desk", "kettle"],
                "answer": "kettle",
                "ground_truth": "B",
            }
        ],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-green\tdoc-green\t1\n",
        encoding="utf-8",
    )
    return convert_mteb_qrels_dry_run(
        tmp_path,
        source_manifest=audit_mteb_source_manifest(
            tmp_path,
            source_revision="0123456789abcdef",
            source_subset="validation",
            declared_license="MIT",
            license_source="synthetic test audit",
        ),
        seed=seed,
    )
