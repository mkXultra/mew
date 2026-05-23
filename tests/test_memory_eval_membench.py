import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from mew.memory_eval import membench as membench_module
from mew.memory_eval.fixtures import split_fixture
from mew.memory_eval.hashing import canonical_json
from mew.memory_eval.membench import (
    MEMBENCH_HF_PROFILE_REVISION,
    MembenchConversionError,
    audit_mteb_source_manifest,
    build_ephemeral_fixtures_from_dry_run,
    build_typed_cards_ephemeral_fixtures_from_dry_run,
    convert_mteb_qrels_dry_run,
    main as membench_main,
    prepare_hf_mteb_qrels_source,
    run_profile,
    validate_mteb_source_manifest,
    validate_mteb_qrels_dry_run,
)


ROOT = Path(__file__).resolve().parents[1]
MEMORY_EVAL_FIXTURES = ROOT / "fixtures" / "memory_eval"
PINNED_SOURCE_REVISION = "0123456789abcdef0123456789abcdef01234567"


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
        source_revision=PINNED_SOURCE_REVISION,
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


def test_mteb_source_manifest_default_private_only_blocks_phase_c_fixture_commit(
    tmp_path,
):
    fixture_tree_before = _fixture_tree_snapshot()
    _write_minimal_mteb_source(tmp_path)

    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision=PINNED_SOURCE_REVISION,
        declared_license="mit",
        license_source="Hugging Face dataset card",
        citation_targets=["mteb/MemBench dataset card", "MTEB"],
    )
    report = validate_mteb_source_manifest(manifest)

    assert manifest["redistribution_status"] == "private_only"
    assert manifest["source_host"] == "Hugging Face"
    assert manifest["source_url"] == "https://huggingface.co/datasets/mteb/MemBench"
    assert manifest["third_party_notice_file"] == "docs/THIRD_PARTY_DATA.md"
    assert report["phase_c_commit_preconditions"] == {
        "status": "private_only",
        "generated_fixture_commit_allowed": False,
        "raw_source_commit_allowed": False,
        "local_evaluation_allowed": True,
        "missing_required_fields": [],
        "reasons": [
            "redistribution_status is private_only; generated fixtures remain local-only"
        ],
    }
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_mteb_source_manifest_commit_allowed_requires_complete_notice_fields(
    tmp_path,
):
    fixture_tree_before = _fixture_tree_snapshot()
    manifest = _commit_allowed_ready_manifest(tmp_path)
    report = validate_mteb_source_manifest(manifest)

    assert report["redistribution_status"] == "commit_allowed"
    assert report["phase_c_commit_preconditions"] == {
        "status": "commit_allowed_ready",
        "generated_fixture_commit_allowed": True,
        "raw_source_commit_allowed": False,
        "local_evaluation_allowed": True,
        "missing_required_fields": [],
        "reasons": [],
    }
    assert report["notice_citation"]["declared_license"] == "mit"
    assert report["provenance"]["raw_file_hash_count"] == 3
    assert report["redistribution_review"] == {
        "approved": True,
        "reviewer": "M6.25 source audit reviewer",
        "reviewed_at": "2026-05-23",
        "decision_basis": (
            "Declared MIT dataset card terms, citation targets, pinned source "
            "revision, local raw-source cache, and no-vendor fixture policy reviewed."
        ),
        "scope": "generated_fixtures_only",
    }
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_mteb_source_manifest_commit_allowed_requires_reviewer_approval_metadata(
    tmp_path,
):
    manifest = _commit_allowed_ready_manifest(tmp_path)
    manifest.pop("redistribution_review")

    report = validate_mteb_source_manifest(manifest)

    preconditions = report["phase_c_commit_preconditions"]
    assert preconditions["status"] == "commit_allowed_not_ready"
    assert preconditions["generated_fixture_commit_allowed"] is False
    assert preconditions["raw_source_commit_allowed"] is False
    assert {
        "redistribution_review.approved:true",
        "redistribution_review.reviewer",
        "redistribution_review.reviewed_at",
        "redistribution_review.decision_basis",
        "redistribution_review.scope:generated_fixtures_only",
    } <= set(preconditions["missing_required_fields"])


@pytest.mark.parametrize(
    ("case_name", "expected_missing_field"),
    [
        ("approval_false", "redistribution_review.approved:true"),
        ("approval_string", "redistribution_review.approved:true"),
        ("missing_reviewer", "redistribution_review.reviewer"),
        ("placeholder_reviewer", "redistribution_review.reviewer"),
        ("missing_reviewed_at", "redistribution_review.reviewed_at"),
        ("placeholder_reviewed_at", "redistribution_review.reviewed_at"),
        ("datetime_reviewed_at", "redistribution_review.reviewed_at"),
        ("invalid_month_reviewed_at", "redistribution_review.reviewed_at"),
        ("invalid_day_reviewed_at", "redistribution_review.reviewed_at"),
        ("missing_decision_basis", "redistribution_review.decision_basis"),
        ("placeholder_decision_basis", "redistribution_review.decision_basis"),
        ("wrong_scope", "redistribution_review.scope:generated_fixtures_only"),
    ],
)
def test_mteb_source_manifest_commit_allowed_rejects_invalid_review_approval(
    tmp_path,
    case_name,
    expected_missing_field,
):
    manifest = _commit_allowed_ready_manifest(tmp_path)
    review = manifest["redistribution_review"]

    if case_name == "approval_false":
        review["approved"] = False
    elif case_name == "approval_string":
        review["approved"] = "true"
    elif case_name == "missing_reviewer":
        review.pop("reviewer")
    elif case_name == "placeholder_reviewer":
        review["reviewer"] = "todo"
    elif case_name == "missing_reviewed_at":
        review.pop("reviewed_at")
    elif case_name == "placeholder_reviewed_at":
        review["reviewed_at"] = "unknown"
    elif case_name == "datetime_reviewed_at":
        review["reviewed_at"] = "2026-05-23T00:00:00Z"
    elif case_name == "invalid_month_reviewed_at":
        review["reviewed_at"] = "2026-99-99"
    elif case_name == "invalid_day_reviewed_at":
        review["reviewed_at"] = "2026-02-30"
    elif case_name == "missing_decision_basis":
        review.pop("decision_basis")
    elif case_name == "placeholder_decision_basis":
        review["decision_basis"] = "source audit required"
    elif case_name == "wrong_scope":
        review["scope"] = "raw_sources"
    else:  # pragma: no cover - protects future parameter additions.
        raise AssertionError(case_name)

    report = validate_mteb_source_manifest(manifest)

    preconditions = report["phase_c_commit_preconditions"]
    assert preconditions["status"] == "commit_allowed_not_ready"
    assert preconditions["generated_fixture_commit_allowed"] is False
    assert expected_missing_field in preconditions["missing_required_fields"]
    assert expected_missing_field in {finding["field"] for finding in report["findings"]}


@pytest.mark.parametrize(
    ("case_name", "expected_missing_field"),
    [
        ("placeholder_source_dataset", "source_dataset"),
        ("placeholder_source_host", "source_host"),
        ("placeholder_source_url", "source_url:absolute"),
        ("relative_source_url", "source_url:absolute"),
        ("placeholder_declared_license", "declared_license"),
        ("placeholder_license_source", "license_source"),
        ("short_revision_marked_pinned", "source_revision:immutable"),
        ("placeholder_license_source_url", "license_source_url:absolute"),
        ("relative_license_source_url", "license_source_url:absolute"),
        (
            "contradictory_generated_fixture_commit_policy",
            "generated_fixture_commit_policy:no_vendor_by_default",
        ),
        (
            "missing_notice_source_provenance_flag",
            "notice_requirements.include_source_provenance",
        ),
        ("short_raw_file_hash", "raw_file_hashes[0]"),
        ("raw_file_hash_without_sha256_prefix", "raw_file_hashes[0]"),
    ],
)
def test_mteb_source_manifest_commit_allowed_rejects_placeholder_or_contradictory_fields(
    tmp_path,
    case_name,
    expected_missing_field,
):
    manifest = _commit_allowed_ready_manifest(tmp_path)

    if case_name == "placeholder_source_dataset":
        manifest["source_dataset"] = "unknown"
    elif case_name == "placeholder_source_host":
        manifest["source_host"] = "todo"
    elif case_name == "placeholder_source_url":
        manifest["source_url"] = "unknown"
    elif case_name == "relative_source_url":
        manifest["source_url"] = "datasets/mteb/MemBench"
    elif case_name == "placeholder_declared_license":
        manifest["declared_license"] = "unknown"
    elif case_name == "placeholder_license_source":
        manifest["license_source"] = "source audit required"
    elif case_name == "short_revision_marked_pinned":
        manifest["source_revision"] = "0123456789abcdef"
        manifest["source_revision_status"] = "pinned"
    elif case_name == "placeholder_license_source_url":
        manifest["license_source_url"] = "source audit required"
    elif case_name == "relative_license_source_url":
        manifest["license_source_url"] = "docs/THIRD_PARTY_DATA.md"
    elif case_name == "contradictory_generated_fixture_commit_policy":
        manifest["generated_fixture_commit_policy"] = "commit_generated_fixtures"
    elif case_name == "missing_notice_source_provenance_flag":
        manifest["notice_requirements"]["include_source_provenance"] = False
    elif case_name == "short_raw_file_hash":
        manifest["raw_file_hashes"][0]["sha256"] = "sha256:abc"
    elif case_name == "raw_file_hash_without_sha256_prefix":
        manifest["raw_file_hashes"][0]["sha256"] = "a" * 64
    else:  # pragma: no cover - protects future parameter additions.
        raise AssertionError(case_name)

    report = validate_mteb_source_manifest(manifest)

    preconditions = report["phase_c_commit_preconditions"]
    assert preconditions["status"] == "commit_allowed_not_ready"
    assert preconditions["generated_fixture_commit_allowed"] is False
    assert expected_missing_field in preconditions["missing_required_fields"]
    assert expected_missing_field in {finding["field"] for finding in report["findings"]}


def test_mteb_source_manifest_commit_allowed_missing_fields_is_not_ready(
    tmp_path,
):
    fixture_tree_before = _fixture_tree_snapshot()
    _write_minimal_mteb_source(tmp_path)

    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision="latest",
        redistribution_status="commit_allowed",
    )
    manifest["citation_targets"] = []
    manifest.pop("third_party_notice_file")
    manifest.pop("notice_requirements")
    report = validate_mteb_source_manifest(manifest)

    preconditions = report["phase_c_commit_preconditions"]
    assert preconditions["status"] == "commit_allowed_not_ready"
    assert preconditions["generated_fixture_commit_allowed"] is False
    assert {
        "source_revision:immutable",
        "source_revision_status:pinned",
        "declared_license",
        "license_source",
        "third_party_notice_file",
        "citation_targets",
    } <= set(preconditions["missing_required_fields"])
    assert {finding["severity"] for finding in report["findings"]} == {"error"}
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_mteb_source_manifest_blocked_prevents_local_and_committed_fixtures(
    tmp_path,
):
    _write_minimal_mteb_source(tmp_path)

    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision=PINNED_SOURCE_REVISION,
        declared_license="mit",
        license_source="Hugging Face dataset card",
        citation_targets=["mteb/MemBench dataset card", "MTEB"],
        redistribution_status="blocked",
    )
    report = validate_mteb_source_manifest(manifest)

    assert report["phase_c_commit_preconditions"]["status"] == "blocked"
    assert (
        report["phase_c_commit_preconditions"][
            "generated_fixture_commit_allowed"
        ]
        is False
    )
    assert report["phase_c_commit_preconditions"]["local_evaluation_allowed"] is False
    assert report["phase_c_commit_preconditions"]["reasons"] == [
        "redistribution_status is blocked"
    ]


def test_mteb_qrels_dry_run_refuses_blocked_source_manifest(tmp_path):
    _write_minimal_mteb_source(tmp_path)
    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision=PINNED_SOURCE_REVISION,
        declared_license="mit",
        license_source="Hugging Face dataset card",
        citation_targets=["mteb/MemBench dataset card", "MTEB"],
        redistribution_status="blocked",
    )

    with pytest.raises(MembenchConversionError, match="blocked"):
        convert_mteb_qrels_dry_run(tmp_path, source_manifest=manifest)


def test_mteb_qrels_dry_run_refuses_invalid_source_manifest_status(tmp_path):
    _write_minimal_mteb_source(tmp_path)
    manifest = audit_mteb_source_manifest(
        tmp_path,
        source_revision=PINNED_SOURCE_REVISION,
        declared_license="mit",
        license_source="Hugging Face dataset card",
        citation_targets=["mteb/MemBench dataset card", "MTEB"],
    )
    manifest["redistribution_status"] = "maybe"

    with pytest.raises(MembenchConversionError, match="invalid"):
        convert_mteb_qrels_dry_run(tmp_path, source_manifest=manifest)


def test_mteb_source_audit_rejects_unknown_redistribution_status(tmp_path):
    _write_minimal_mteb_source(tmp_path)

    with pytest.raises(ValueError, match="redistribution_status"):
        audit_mteb_source_manifest(
            tmp_path,
            source_revision=PINNED_SOURCE_REVISION,
            redistribution_status="maybe",
        )


def test_mteb_audit_source_cli_records_review_approval_metadata(tmp_path):
    _write_minimal_mteb_source(tmp_path)
    output_path = tmp_path / "source_manifest.json"

    assert (
        membench_main(
            [
                "audit-source",
                str(tmp_path),
                "--source-revision",
                PINNED_SOURCE_REVISION,
                "--declared-license",
                "mit",
                "--license-source",
                "Hugging Face dataset card",
                "--license-source-url",
                "https://huggingface.co/datasets/mteb/MemBench",
                "--citation-target",
                "mteb/MemBench dataset card",
                "--redistribution-status",
                "commit_allowed",
                "--redistribution-review-approved",
                "--redistribution-reviewer",
                "M6.25 source audit reviewer",
                "--redistribution-reviewed-at",
                "2026-05-23",
                "--redistribution-decision-basis",
                "Pinned source, declared license, citations, and no-vendor policy reviewed.",
                "--redistribution-review-scope",
                "generated_fixtures_only",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    manifest = json.loads(output_path.read_text(encoding="utf-8"))
    report = validate_mteb_source_manifest(manifest)

    assert manifest["redistribution_review"]["approved"] is True
    assert report["phase_c_commit_preconditions"]["status"] == "commit_allowed_ready"
    assert report["phase_c_commit_preconditions"]["raw_source_commit_allowed"] is False


def test_mteb_validate_source_manifest_cli_reports_phase_c_status(
    tmp_path, capsys
):
    manifest = _commit_allowed_ready_manifest(tmp_path)
    manifest_path = tmp_path / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    assert (
        membench_main(
            [
                "validate-source-manifest",
                str(manifest_path),
                "--require-commit-allowed",
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "mew_membench_source_audit_report.v1"
    assert output["phase_c_commit_preconditions"]["status"] == (
        "commit_allowed_ready"
    )
    assert output["phase_c_commit_preconditions"][
        "generated_fixture_commit_allowed"
    ] is True


def test_prepare_hf_mteb_qrels_writes_local_jsonl_and_private_manifest(tmp_path):
    fixture_tree_before = _fixture_tree_snapshot()
    calls = []

    prepared = prepare_hf_mteb_qrels_source(
        tmp_path / "hf_source",
        revision=PINNED_SOURCE_REVISION,
        include_top_ranked=True,
        declared_license="mit",
        license_source="synthetic test audit",
        loader=_fake_hf_mteb_loader(calls),
    )

    assert prepared.manifest_path == tmp_path / "hf_source" / "source_manifest.json"
    assert prepared.top_ranked_path == tmp_path / "hf_source" / "top_ranked.jsonl"
    assert [call["config_name"] for call in calls] == [
        "single_hop-corpus",
        "single_hop-queries",
        "single_hop-qrels",
        "single_hop-top_ranked",
    ]
    assert json.loads(prepared.corpus_path.read_text(encoding="utf-8").splitlines()[0])[
        "_id"
    ] == "doc-green"
    assert json.loads(prepared.queries_path.read_text(encoding="utf-8").splitlines()[0])[
        "_id"
    ] == "query-green"
    assert json.loads(prepared.qrels_path.read_text(encoding="utf-8").splitlines()[0])[
        "corpus-id"
    ] == "doc-green"

    manifest = json.loads(prepared.manifest_path.read_text(encoding="utf-8"))
    report = validate_mteb_source_manifest(manifest)

    assert manifest["source_dataset"] == "mteb/MemBench"
    assert manifest["source_subset"] == "single_hop"
    assert manifest["source_revision"] == PINNED_SOURCE_REVISION
    assert manifest["source_revision_status"] == "pinned"
    assert manifest["local_cache_only"] is True
    assert manifest["generated_fixture_commit_policy"] == "no_vendor_by_default"
    assert manifest["redistribution_status"] == "private_only"
    assert manifest["hf_mteb_export"] == {
        "dataset": "mteb/MemBench",
        "subset": "single_hop",
        "revision": PINNED_SOURCE_REVISION,
        "split": "auto",
        "config_names": {
            "corpus": "single_hop-corpus",
            "queries": "single_hop-queries",
            "qrels": "single_hop-qrels",
            "top_ranked": "single_hop-top_ranked",
        },
        "include_top_ranked": True,
        "raw_source_policy": "local_only_no_vendor",
        "writes_generated_fixtures": False,
    }
    assert {item["path"] for item in manifest["raw_file_hashes"]} == {
        "corpus.jsonl",
        "queries.jsonl",
        "qrels.jsonl",
        "top_ranked.jsonl",
    }
    assert report["phase_c_commit_preconditions"]["status"] == "private_only"
    assert (
        report["phase_c_commit_preconditions"]["generated_fixture_commit_allowed"]
        is False
    )
    assert report["phase_c_commit_preconditions"]["raw_source_commit_allowed"] is False
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_prepare_hf_mteb_qrels_output_feeds_dry_run_and_validation(tmp_path):
    fixture_tree_before = _fixture_tree_snapshot()
    prepared = prepare_hf_mteb_qrels_source(
        tmp_path / "hf_source",
        revision=PINNED_SOURCE_REVISION,
        loader=_fake_hf_mteb_loader([]),
    )

    dry_run = convert_mteb_qrels_dry_run(
        prepared.source_dir,
        manifest_path=prepared.manifest_path,
        max_queries=1,
    )
    validation = validate_mteb_qrels_dry_run(dry_run)

    assert dry_run["candidate_counts"]["selected_fixture_previews"] == 1
    assert dry_run["source_manifest"]["redistribution_status"] == "private_only"
    assert (
        dry_run["commit_policy"]["phase_c_generated_fixture_commit_allowed"] is False
    )
    assert validation["validation_status"] == "passed"
    assert validation["ephemeral_fixture_policy"]["writes_fixture_pack"] is False
    assert (
        validation["ephemeral_fixture_policy"]["generated_fixture_pack_committed"]
        is False
    )
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_mteb_profile_runs_setup_and_validation_with_fake_loader(tmp_path):
    fixture_tree_before = _fixture_tree_snapshot()
    calls = []

    report = run_profile(
        "membench-smoke200-typed",
        work_dir=tmp_path / "profiles",
        loader=_fake_hf_mteb_loader(calls),
    )

    assert [call["config_name"] for call in calls] == [
        "single_hop-corpus",
        "single_hop-queries",
        "single_hop-qrels",
    ]
    assert {call["revision"] for call in calls} == {MEMBENCH_HF_PROFILE_REVISION}
    assert report["schema_version"] == "mew_membench_profile_run.v1"
    assert report["profile"] == "membench-smoke200-typed"
    assert report["profile_config"] == {
        "corpus_sample_policy": "qrel_plus_prefix",
        "dataset": "mteb/MemBench",
        "include_typed_cards": True,
        "max_corpus_docs": 200,
        "max_queries": 1,
        "revision": MEMBENCH_HF_PROFILE_REVISION,
        "subset": "single_hop",
    }
    assert report["phases"]["setup.prepare"]["status"] == "passed"
    assert report["phases"]["setup.source_gate"]["status"] == "private_only"
    assert report["phases"]["setup.dry_run"]["status"] == "passed"
    assert report["phases"]["run.validation"]["qrels_oracle"]["passed"] is True
    assert report["summary"]["setup_passed"] is True
    assert report["summary"]["qrels_oracle_passed"] is True
    assert report["commit_policy"] == {
        "generated_fixture_pack_committed": False,
        "profile_artifacts_local_only": True,
        "raw_source_committed": False,
    }
    assert (tmp_path / "profiles" / "membench-smoke200-typed" / "dry_run.json").exists()
    assert (
        tmp_path / "profiles" / "membench-smoke200-typed" / "validation.json"
    ).exists()
    assert (
        tmp_path / "profiles" / "membench-smoke200-typed" / "profile_report.json"
    ).exists()
    assert fixture_tree_before == _fixture_tree_snapshot()


def test_prepare_hf_mteb_qrels_missing_datasets_cli_message(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setitem(sys.modules, "datasets", None)

    assert (
        membench_main(
            [
                "prepare-hf-mteb-qrels",
                str(tmp_path / "hf_source"),
                "--revision",
                PINNED_SOURCE_REVISION,
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "Development dependency 'datasets' is required" in captured.err
    assert not (tmp_path / "hf_source").exists()


def test_prepare_hf_mteb_qrels_old_datasets_cli_message(
    tmp_path, monkeypatch, capsys
):
    calls = []

    def fake_load_dataset(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("load_dataset should not be called without DownloadConfig")

    monkeypatch.setitem(
        sys.modules,
        "datasets",
        SimpleNamespace(load_dataset=fake_load_dataset),
    )

    assert (
        membench_main(
            [
                "prepare-hf-mteb-qrels",
                str(tmp_path / "hf_source"),
                "--revision",
                PINNED_SOURCE_REVISION,
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "must support DownloadConfig(local_files_only=True)" in captured.err
    assert calls == []
    assert not (tmp_path / "hf_source").exists()


def test_default_hf_dataset_loader_requests_local_files_only(monkeypatch):
    calls = []

    class FakeDownloadConfig:
        def __init__(self, *, local_files_only):
            self.local_files_only = local_files_only

    def fake_load_dataset(dataset, config_name, *, revision, download_config):
        calls.append(
            {
                "dataset": dataset,
                "config_name": config_name,
                "revision": revision,
                "download_config": download_config,
            }
        )
        return [{"_id": "doc-1", "text": "cached record"}]

    monkeypatch.setitem(
        sys.modules,
        "datasets",
        SimpleNamespace(
            DownloadConfig=FakeDownloadConfig,
            load_dataset=fake_load_dataset,
        ),
    )

    result = membench_module._default_hf_dataset_loader(
        "mteb/MemBench",
        "single_hop-corpus",
        revision=PINNED_SOURCE_REVISION,
    )

    assert result == [{"_id": "doc-1", "text": "cached record"}]
    assert len(calls) == 1
    call = calls[0]
    assert call["dataset"] == "mteb/MemBench"
    assert call["config_name"] == "single_hop-corpus"
    assert call["revision"] == PINNED_SOURCE_REVISION
    assert isinstance(call["download_config"], FakeDownloadConfig)
    assert call["download_config"].local_files_only is True


def test_prepare_hf_mteb_qrels_requires_pinned_revision_before_loading(tmp_path):
    calls = []

    with pytest.raises(MembenchConversionError, match="40-character commit SHA"):
        prepare_hf_mteb_qrels_source(
            tmp_path / "hf_source",
            revision="main",
            loader=_fake_hf_mteb_loader(calls),
        )

    assert calls == []
    assert not (tmp_path / "hf_source").exists()


def test_prepare_hf_mteb_qrels_rejects_fixture_output_dir(tmp_path):
    fixture_tree_before = _fixture_tree_snapshot()

    with pytest.raises(MembenchConversionError, match="outside fixtures/memory_eval"):
        prepare_hf_mteb_qrels_source(
            MEMORY_EVAL_FIXTURES / "membench_raw_source",
            revision=PINNED_SOURCE_REVISION,
            loader=_fake_hf_mteb_loader([]),
        )

    assert fixture_tree_before == _fixture_tree_snapshot()


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
        source_revision=PINNED_SOURCE_REVISION,
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


def test_mteb_qrels_dry_run_can_sample_qrel_plus_prefix_corpus(tmp_path):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {"_id": "doc-a", "text": "Aki keeps green tea nearby."},
            {"_id": "doc-b", "text": "Rin stores a blue bicycle."},
            {"_id": "doc-c", "text": "Kai prefers window seats."},
            {"_id": "doc-target", "text": "Mina keeps the bronze key."},
        ],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"_id": "query-key", "text": "Which item does Mina keep?"}],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-key\tdoc-target\t1\n",
        encoding="utf-8",
    )

    report = convert_mteb_qrels_dry_run(
        tmp_path,
        source_manifest=audit_mteb_source_manifest(
            tmp_path, source_revision=PINNED_SOURCE_REVISION
        ),
        corpus_sample_policy="qrel_plus_prefix",
        max_corpus_docs=2,
    )

    preview = report["fixture_previews"][0]
    scorer_request = preview["scorer_view"]["requests"][0]

    assert report["corpus_sampling"]["policy"] == "qrel_plus_prefix"
    assert report["candidate_counts"]["corpus_documents"] == 4
    assert report["candidate_counts"]["effective_corpus_documents_min"] == 2
    assert len(preview["scorer_view"]["experiences"]) == 2
    assert scorer_request["gold"]["relevant_evidence_ids"] == ["exp_src_000001"]
    assert scorer_request["gold"]["corpus_sampling"] == {
        "effective_corpus_docs": 2,
        "max_corpus_docs": 2,
        "policy": "qrel_plus_prefix",
        "qrel_doc_count": 1,
        "qrel_docs_included": True,
        "total_corpus_docs": 4,
    }
    assert preview["adapter_view"]["experiences"][0]["payload"]["text"] == (
        "Mina keeps the bronze key."
    )
    assert validate_mteb_qrels_dry_run(report)["validation_status"] == "passed"


def test_mteb_qrels_dry_run_random_sampling_is_seed_stable(tmp_path):
    _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {"_id": "doc-a", "text": "Aki keeps green tea nearby."},
            {"_id": "doc-b", "text": "Rin stores a blue bicycle."},
            {"_id": "doc-c", "text": "Kai prefers window seats."},
            {"_id": "doc-d", "text": "Noa labels the red folder."},
            {"_id": "doc-target", "text": "Mina keeps the bronze key."},
        ],
    )
    _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"_id": "query-key", "text": "Which item does Mina keep?"}],
    )
    (tmp_path / "qrels.tsv").write_text(
        "query-id\tcorpus-id\tscore\nquery-key\tdoc-target\t1\n",
        encoding="utf-8",
    )
    manifest = audit_mteb_source_manifest(
        tmp_path, source_revision=PINNED_SOURCE_REVISION
    )

    first = convert_mteb_qrels_dry_run(
        tmp_path,
        source_manifest=manifest,
        corpus_sample_policy="qrel_plus_random",
        max_corpus_docs=3,
        seed=7,
    )
    second = convert_mteb_qrels_dry_run(
        tmp_path,
        source_manifest=manifest,
        corpus_sample_policy="qrel_plus_random",
        max_corpus_docs=3,
        seed=7,
    )

    assert first["fixture_previews"][0]["fixture_full_hash"] == (
        second["fixture_previews"][0]["fixture_full_hash"]
    )
    assert first["candidate_counts"]["effective_corpus_documents_max"] == 3


def test_mteb_qrels_dry_run_requires_sample_size_for_sampling(tmp_path):
    _write_minimal_mteb_source(tmp_path)

    with pytest.raises(MembenchConversionError, match="max-corpus-docs"):
        convert_mteb_qrels_dry_run(
            tmp_path,
            source_manifest=audit_mteb_source_manifest(
                tmp_path, source_revision=PINNED_SOURCE_REVISION
            ),
            corpus_sample_policy="qrel_plus_prefix",
        )


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
            tmp_path, source_revision=PINNED_SOURCE_REVISION
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
            tmp_path, source_revision=PINNED_SOURCE_REVISION
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


def _fake_hf_mteb_loader(calls):
    records = {
        "single_hop-corpus": [
            {
                "_id": "doc-green",
                "title": "Tea note",
                "text": "Aki's family stores the green tea tin beside the kettle.",
            },
            {
                "_id": "doc-bike",
                "text": "Rin parks the blue bicycle near the station gate.",
            },
        ],
        "single_hop-queries": [
            {
                "_id": "query-green",
                "text": "Where does Aki store the green tea tin?",
                "choices": ["desk", "kettle"],
                "answer": "kettle",
                "ground_truth": "B",
            }
        ],
        "single_hop-qrels": [
            {"query-id": "query-green", "corpus-id": "doc-green", "score": 1}
        ],
        "single_hop-top_ranked": [
            {"query-id": "query-green", "corpus-id": "doc-bike", "score": 0.2}
        ],
    }

    def loader(dataset, config_name, *, revision):
        calls.append(
            {
                "dataset": dataset,
                "config_name": config_name,
                "revision": revision,
            }
        )
        return {"test": records[config_name]}

    return loader


def _write_minimal_mteb_source(tmp_path):
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


def _commit_allowed_ready_manifest(tmp_path):
    _write_minimal_mteb_source(tmp_path)
    return audit_mteb_source_manifest(
        tmp_path,
        source_revision=PINNED_SOURCE_REVISION,
        declared_license="mit",
        license_source="Hugging Face dataset card",
        license_source_url="https://huggingface.co/datasets/mteb/MemBench",
        citation_targets=[
            "mteb/MemBench dataset card",
            "LMEB",
            "MMTEB",
            "MTEB",
        ],
        redistribution_status="commit_allowed",
        redistribution_review_approved=True,
        redistribution_reviewer="M6.25 source audit reviewer",
        redistribution_reviewed_at="2026-05-23",
        redistribution_decision_basis=(
            "Declared MIT dataset card terms, citation targets, pinned source "
            "revision, local raw-source cache, and no-vendor fixture policy reviewed."
        ),
        redistribution_review_scope="generated_fixtures_only",
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
            source_revision=PINNED_SOURCE_REVISION,
            source_subset="validation",
            declared_license="MIT",
            license_source="synthetic test audit",
        ),
        seed=seed,
    )
