import json
from copy import deepcopy

from mew.memory_eval.fixtures import split_fixture
from mew.memory_eval.hashing import canonical_json
from mew.memory_eval.membench import (
    audit_mteb_source_manifest,
    convert_mteb_qrels_dry_run,
)


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

    assert report["candidate_counts"]["selected_fixture_previews"] == 1
    assert report["candidate_counts"]["skipped_examples"] == 0
    assert report["adapter_view_check_summary"] == {
        "passed": True,
        "fixture_count": 1,
        "failure_count": 0,
    }
    preview = report["fixture_previews"][0]
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
