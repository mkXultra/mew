"""MemBench external-source audit and MTEB qrels dry-run conversion.

This module intentionally supports local/cache-only dry runs. It does not
download MemBench data, vendor raw sources, or write committed fixture packs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .adapters.broken import (
    DuplicateSupportAdapter,
    MissingUsageAdapter,
    SupportSourceMismatchAdapter,
    UnscorableEvidenceAdapter,
)
from .adapter_contract import adapter_manifest, default_capabilities, default_usage
from .fixtures import FIXTURE_SCHEMA_VERSION, split_fixture
from .hashing import stable_hash
from .runner import run_fixture


SOURCE_MANIFEST_SCHEMA_VERSION = "mew_membench_source_manifest.v1"
SOURCE_AUDIT_REPORT_SCHEMA_VERSION = "mew_membench_source_audit_report.v1"
DRY_RUN_SCHEMA_VERSION = "mew_membench_mteb_qrels_dry_run.v1"
DRY_RUN_VALIDATION_SCHEMA_VERSION = "mew_membench_dry_run_validation.v1"
CONVERTER_ID = "mew_membench_mteb_qrels_converter"
CONVERTER_VERSION = "0.1.0"
MEMBENCH_HF_DATASET = "mteb/MemBench"
MEMBENCH_HF_SOURCE_HOST = "Hugging Face"
MEMBENCH_HF_DATASET_URL = "https://huggingface.co/datasets/mteb/MemBench"
MEMBENCH_THIRD_PARTY_NOTICE_FILE = "docs/THIRD_PARTY_DATA.md"
MEMORY_EVAL_FIXTURES_DIR = (
    Path(__file__).resolve().parents[3] / "fixtures" / "memory_eval"
)
DEFAULT_EVALUATION_TIME = "2026-05-22T00:00:00Z"
DEFAULT_SCOPE_ID = "tenant_mb/user_000001"
DEFAULT_QUERY_TIME = "2026-05-22T00:00:00Z"
DEFAULT_VALIDATION_CREATED_AT = "2026-05-22T00:00:00Z"
REDISTRIBUTION_STATUSES = ("private_only", "commit_allowed", "blocked")
REDISTRIBUTION_REVIEW_SCOPE = "generated_fixtures_only"
CORPUS_SAMPLE_POLICIES = ("full", "qrel_plus_prefix", "qrel_plus_random")
TYPED_CARDS_SUMMARY_SEARCH_BACKENDS = (
    "direct_scan_lexical",
    "bm25",
    "vector",
    "hybrid",
)
TYPED_CARDS_EXTRACTOR_MODES = ("deterministic_replay", "live_model")
TYPED_CARDS_VECTOR_BACKENDS = {"vector", "hybrid"}
DEFAULT_TYPED_CARDS_EMBEDDING_PROVIDER = "ollama"
DEFAULT_TYPED_CARDS_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
DEFAULT_TYPED_CARDS_LIVE_BACKEND = "codex"
DEFAULT_TYPED_CARDS_LIVE_MODEL = "gpt-5.5"
DEFAULT_TYPED_CARDS_LIVE_AUTH_JSON = Path.home() / ".codex" / "auth.json"
DEFAULT_TYPED_CARDS_LIVE_CALL_INTERFACE = "call_model_structured_json"
DEFAULT_TYPED_CARDS_LIVE_TIMEOUT = 120
DEFAULT_TYPED_CARDS_LIVE_OUTPUT_DIR = Path("tmp/membench-live-model")
PROFILE_SCHEMA_VERSION = "mew_membench_profile_run.v1"
# Pinned Hugging Face dataset commit for `mteb/MemBench` used by the
# MemBench profiles. This is a dataset revision, not a code release; pinning it
# keeps local source hashes and dry-run artifacts stable.
MEMBENCH_HF_PROFILE_REVISION = "1dd519e4d91573e2818d850eb4405fb290663ac2"
PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "membench-smoke200-typed": {
        "subset": "single_hop",
        "max_queries": 1,
        "corpus_sample_policy": "qrel_plus_prefix",
        "max_corpus_docs": 200,
        "include_typed_cards": True,
    },
    "membench-sample1000-typed": {
        "subset": "single_hop",
        "max_queries": 10,
        "corpus_sample_policy": "qrel_plus_prefix",
        "max_corpus_docs": 1000,
        "include_typed_cards": True,
    },
    "membench-full-qrels-oracle": {
        "subset": "single_hop",
        "max_queries": None,
        "corpus_sample_policy": "full",
        "max_corpus_docs": None,
        "include_typed_cards": False,
    },
    "membench-sample5000-typed": {
        "subset": "single_hop",
        "max_queries": 50,
        "corpus_sample_policy": "qrel_plus_prefix",
        "max_corpus_docs": 5000,
        "include_typed_cards": True,
    },
    "membench-full-typed": {
        "subset": "single_hop",
        "max_queries": None,
        "corpus_sample_policy": "full",
        "max_corpus_docs": None,
        "include_typed_cards": True,
    },
}
PROFILE_NAMES = tuple(PROFILE_CONFIGS)
UNPINNED_REVISION_VALUES = {"", "latest", "main", "master", "unresolved"}
PINNED_REVISION_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_DIGEST_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
REVIEWED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER_TEXT_VALUES = {
    "",
    "...",
    "n/a",
    "none",
    "placeholder",
    "source audit required",
    "tbd",
    "todo",
    "unknown",
    "unreviewed",
    "unresolved",
}

CORPUS_ID_KEYS = ("_id", "id", "doc_id", "docid", "corpus_id", "corpus-id")
QUERY_ID_KEYS = ("_id", "id", "query_id", "query-id", "qid")
QREL_QUERY_ID_KEYS = ("query-id", "query_id", "qid", "query")
QREL_DOC_ID_KEYS = ("corpus-id", "corpus_id", "doc_id", "docid", "pid", "document_id")
QREL_SCORE_KEYS = ("score", "relevance", "relevance_score")

SCORER_ONLY_FIELD_PATHS = [
    "source_benchmark",
    "requests[].mode",
    "requests[].requires_capabilities",
    "requests[].on_unsupported",
    "requests[].gold",
    "requests[].gold.relevant_evidence_ids",
    "requests[].gold.acceptable_support_sets",
    "requests[].gold.support_coverage_policy",
    "requests[].gold.source_qrels",
]

REQUEST_PUBLIC_FIELD_NAMES = (
    "scope_id",
    "query_time",
    "query",
    "k",
    "filters",
    "budget",
)

REQUEST_SCORER_FIELD_NAMES = (
    "mode",
    "requires_capabilities",
    "on_unsupported",
    "gold",
    "expected_failure_types",
)

MEMBENCH_PRIVATE_STRUCTURAL_KEYS = {
    "answer",
    "answer_artifact_gold",
    "attr",
    "category",
    "choices",
    "corpus_id",
    "doc_id",
    "ground_truth",
    "memory_index",
    "mode",
    "qid",
    "query_id",
    "qrel",
    "qrels",
    "rel",
    "source_benchmark",
    "source_doc_id",
    "source_locator",
    "source_locator_hash",
    "source_path",
    "source_qrels",
    "target_step_id",
    "value",
}

MEMBENCH_PRIVATE_VALUE_TOKENS = {
    "answer=",
    "attr=",
    "choices=",
    "ground_truth",
    "memory_index",
    "qrels",
    "rel=",
    "source_benchmark",
    "source_locator",
    "source_path",
    "source_qrels",
    "target_step_id",
    "value=",
}


class MembenchConversionError(ValueError):
    """Raised when a local source cannot be interpreted as MTEB qrels data."""


HfDatasetLoader = Callable[..., Any]


class _MembenchQrelsOracleAdapter:
    """Validation-only adapter that replays scorer qrels through public IDs."""

    def __init__(self, support_by_adapter_request_id: Mapping[str, Sequence[str]]):
        self._support_by_adapter_request_id = {
            str(request_id): [str(item) for item in support_ids]
            for request_id, support_ids in support_by_adapter_request_id.items()
        }
        self._items: dict[str, dict[str, Any]] = {}

    def manifest(self) -> dict[str, Any]:
        return adapter_manifest(
            adapter_id="membench_qrels_oracle_reference",
            memory_implementation_id="membench_qrels_oracle_reference",
            capability_tier="retrieval_only",
            capabilities=default_capabilities(
                scope_enforcement=True,
                latency_reporting=True,
            ),
        )

    def reset(self, run: Mapping[str, Any]) -> dict[str, Any]:
        self._items = {}
        return {"status": "success", "fixture_id": run.get("fixture_id"), "failures": []}

    def ingest(self, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        receipts = []
        for item in items:
            experience_id = str(item.get("experience_id") or "")
            self._items[experience_id] = dict(item)
            receipts.append(
                {"experience_id": experience_id, "status": "success", "failures": []}
            )
        return receipts

    def mutate(self, ops: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"op_id": str(op.get("op_id") or ""), "status": "success", "failures": []}
            for op in ops
        ]

    def retrieve(self, query: Mapping[str, Any]) -> dict[str, Any]:
        request_id = str(query.get("request_id") or "")
        k = int(query.get("k") or 5)
        budget = query.get("budget") or {}
        if budget.get("max_evidence_items") is not None:
            k = min(k, int(budget.get("max_evidence_items")))
        ranked = []
        for evidence_id in self._support_by_adapter_request_id.get(request_id, [])[:k]:
            item = self._items.get(evidence_id)
            if item is None:
                continue
            ranked.append(
                {
                    "evidence_ref": f"mem_{evidence_id}",
                    "evidence_id": evidence_id,
                    "rank": len(ranked) + 1,
                    "score": None,
                    "score_type": "none",
                    "support_experience_ids": [evidence_id],
                    "source_mutation_ids": [],
                    "state": "active",
                    "scope_id": item.get("scope_id"),
                }
            )
        return {
            "request_id": query.get("request_id"),
            "ranked_evidence": ranked,
            "abstained": not ranked,
            "abstained_reason": "no_memory" if not ranked else None,
            "dropped": [],
            "usage": default_usage(latency_ms=0.0),
            "failures": [],
        }

    def report_usage(self, scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return default_usage(latency_ms=0.0)


@dataclass(frozen=True)
class PreparedMtebSource:
    source_dir: Path
    corpus_path: Path
    queries_path: Path
    qrels_path: Path
    top_ranked_path: Path | None = None
    manifest_path: Path | None = None


def audit_mteb_source_manifest(
    source_dir: str | Path,
    *,
    manifest_path: str | Path | None = None,
    source_dataset: str = MEMBENCH_HF_DATASET,
    source_host: str | None = None,
    source_url: str | None = None,
    source_revision: str | None = None,
    source_subset: str | Iterable[str] | None = None,
    declared_license: str | None = None,
    license_source: str | None = None,
    license_source_url: str | None = None,
    citation_required: bool = True,
    citation_targets: Iterable[str] | None = None,
    third_party_notice_file: str | None = None,
    redistribution_status: str | None = None,
    redistribution_review_approved: bool | None = None,
    redistribution_reviewer: str | None = None,
    redistribution_reviewed_at: str | None = None,
    redistribution_decision_basis: str | None = None,
    redistribution_review_scope: str | None = None,
) -> dict[str, Any]:
    """Build a conservative external-source manifest from local cached files.

    Caller-supplied values override values from an optional manifest file. The
    result records declared source metadata but deliberately does not assert
    legal certainty.
    """

    root = Path(source_dir)
    existing = (
        _load_json_object(manifest_path)
        if manifest_path
        else _load_default_manifest(root)
    )
    source_files = _find_source_files(root, existing)
    raw_hashes = _raw_file_hashes(source_files)
    subset = _source_subset_value(
        source_subset if source_subset is not None else existing.get("source_subset")
    )
    source_host_value = (
        source_host
        if source_host is not None
        else existing.get("source_host") or MEMBENCH_HF_SOURCE_HOST
    )
    source_url_value = (
        source_url
        if source_url is not None
        else existing.get("source_url") or MEMBENCH_HF_DATASET_URL
    )
    revision = (
        source_revision
        if source_revision is not None
        else existing.get("source_revision")
    )
    license_value = (
        declared_license
        if declared_license is not None
        else existing.get("declared_license")
    )
    license_origin = (
        license_source if license_source is not None else existing.get("license_source")
    )
    license_url = (
        license_source_url
        if license_source_url is not None
        else existing.get("license_source_url") or source_url_value
    )
    targets = (
        list(citation_targets)
        if citation_targets is not None
        else list(existing.get("citation_targets") or [])
    )
    if not targets:
        targets = ["mteb/MemBench dataset card", "MTEB"]
    notice_file = (
        third_party_notice_file
        if third_party_notice_file is not None
        else existing.get("third_party_notice_file")
        or existing.get("notice_file")
        or MEMBENCH_THIRD_PARTY_NOTICE_FILE
    )
    redistribution_status_value = _validated_redistribution_status(
        redistribution_status
        if redistribution_status is not None
        else existing.get("redistribution_status")
        or "private_only"
    )
    redistribution_review = _redistribution_review_manifest(
        existing=existing.get("redistribution_review"),
        approved=redistribution_review_approved,
        reviewer=redistribution_reviewer,
        reviewed_at=redistribution_reviewed_at,
        decision_basis=redistribution_decision_basis,
        scope=redistribution_review_scope,
    )

    warnings = []
    if not _is_pinned_revision(revision):
        warnings.append("source_revision is not pinned to an immutable revision")
    if not license_value:
        warnings.append(
            "declared_license is missing; redistribution remains unresolved"
        )
    if not raw_hashes:
        warnings.append("no local raw source files were found for hashing")
    if redistribution_status_value == "blocked":
        warnings.append(
            "redistribution_status is blocked; generated fixture commits are disallowed"
        )

    manifest = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "source_mode": "external_huggingface",
        "source_dataset": source_dataset,
        "source_host": source_host_value,
        "source_url": source_url_value,
        "source_revision": revision or "unresolved",
        "source_revision_status": "pinned"
        if _is_pinned_revision(revision)
        else "unresolved",
        "source_subset": subset,
        "declared_license": license_value or "unreviewed",
        "license_source": license_origin or "source audit required",
        "license_source_url": license_url or "source audit required",
        "license_certainty": "declared_unverified" if license_value else "unknown",
        "citation_required": bool(citation_required),
        "citation_targets": targets,
        "local_cache_only": True,
        "generated_fixture_commit_policy": "no_vendor_by_default",
        "third_party_notice_file": notice_file,
        "notice_requirements": {
            "notice_file": notice_file,
            "required_if_generated_fixtures_committed": True,
            "include_declared_license": True,
            "include_citation_targets": True,
            "include_source_provenance": True,
        },
        "redistribution_status": redistribution_status_value,
        "redistribution_status_options": list(REDISTRIBUTION_STATUSES),
        "redistribution_certainty": "reviewer_required",
        "redistribution_review": redistribution_review,
        "notice_file_required_if_committed": True,
        "raw_file_hashes": raw_hashes,
        "raw_file_hash_status": "present" if raw_hashes else "missing",
        "source_files": _source_file_manifest(source_files),
        "audit_warnings": warnings,
    }
    manifest["source_manifest_hash"] = stable_hash(
        {key: value for key, value in manifest.items() if key != "source_manifest_hash"}
    )
    return manifest


def validate_mteb_source_manifest(
    source_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Report whether a MemBench source manifest permits Phase C fixture commits."""

    manifest = dict(source_manifest)
    status_value = str(manifest.get("redistribution_status") or "private_only")
    findings: list[dict[str, Any]] = []
    if status_value not in REDISTRIBUTION_STATUSES:
        findings.append(
            _source_audit_finding(
                severity="error",
                field="redistribution_status",
                message=(
                    f"redistribution_status {status_value!r} is not one of "
                    f"{', '.join(REDISTRIBUTION_STATUSES)}"
                ),
            )
        )
        status = "invalid"
    else:
        status = status_value

    missing_commit_fields: list[str] = []
    if status == "commit_allowed":
        missing_commit_fields = _missing_phase_c_commit_fields(manifest)
        for field in missing_commit_fields:
            findings.append(
                _source_audit_finding(
                    severity="error",
                    field=field,
                    message=(
                        f"{field} is required before generated MemBench-derived "
                        "fixtures may be committed"
                    ),
                )
            )

    if status == "invalid":
        phase_c_status = "invalid"
        commit_allowed = False
        local_evaluation_allowed = False
        reasons = ["unrecognized redistribution_status"]
    elif status == "blocked":
        phase_c_status = "blocked"
        commit_allowed = False
        local_evaluation_allowed = False
        reasons = ["redistribution_status is blocked"]
    elif status == "private_only":
        phase_c_status = "private_only"
        commit_allowed = False
        local_evaluation_allowed = True
        reasons = [
            "redistribution_status is private_only; generated fixtures remain local-only"
        ]
    elif missing_commit_fields:
        phase_c_status = "commit_allowed_not_ready"
        commit_allowed = False
        local_evaluation_allowed = True
        reasons = [
            "commit_allowed requires complete notice, citation, provenance, "
            "and reviewer approval fields"
        ]
    else:
        phase_c_status = "commit_allowed_ready"
        commit_allowed = True
        local_evaluation_allowed = True
        reasons = []

    report = {
        "schema_version": SOURCE_AUDIT_REPORT_SCHEMA_VERSION,
        "source_dataset": manifest.get("source_dataset") or MEMBENCH_HF_DATASET,
        "source_host": manifest.get("source_host") or MEMBENCH_HF_SOURCE_HOST,
        "source_url": manifest.get("source_url"),
        "source_manifest_hash": manifest.get("source_manifest_hash")
        or stable_hash(manifest),
        "redistribution_status": status_value,
        "redistribution_status_options": list(REDISTRIBUTION_STATUSES),
        "phase_c_commit_preconditions": {
            "status": phase_c_status,
            "generated_fixture_commit_allowed": commit_allowed,
            "raw_source_commit_allowed": False,
            "local_evaluation_allowed": local_evaluation_allowed,
            "missing_required_fields": missing_commit_fields,
            "reasons": reasons,
        },
        "notice_citation": {
            "third_party_notice_file": manifest.get("third_party_notice_file")
            or (manifest.get("notice_requirements") or {}).get("notice_file"),
            "declared_license": manifest.get("declared_license"),
            "license_source": manifest.get("license_source"),
            "license_source_url": manifest.get("license_source_url"),
            "citation_required": bool(manifest.get("citation_required")),
            "citation_targets": list(manifest.get("citation_targets") or []),
        },
        "provenance": {
            "source_revision": manifest.get("source_revision"),
            "source_revision_status": manifest.get("source_revision_status"),
            "raw_file_hash_status": manifest.get("raw_file_hash_status"),
            "raw_file_hash_count": len(manifest.get("raw_file_hashes") or []),
            "local_cache_only": bool(manifest.get("local_cache_only")),
            "generated_fixture_commit_policy": manifest.get(
                "generated_fixture_commit_policy"
            ),
        },
        "redistribution_review": dict(
            manifest.get("redistribution_review")
            if isinstance(manifest.get("redistribution_review"), Mapping)
            else {}
        ),
        "findings": findings,
        "legal_review_note": (
            "This report records source-audit metadata and declared upstream "
            "fields; it is not legal advice."
        ),
    }
    report["source_audit_report_hash"] = stable_hash(
        {
            key: value
            for key, value in report.items()
            if key != "source_audit_report_hash"
        }
    )
    return report


def _raise_if_source_audit_blocks_conversion(
    source_audit_report: Mapping[str, Any],
) -> None:
    preconditions = source_audit_report.get("phase_c_commit_preconditions") or {}
    status = str(preconditions.get("status") or "")
    if status in {"blocked", "invalid"}:
        raise MembenchConversionError(
            "MemBench source manifest is not eligible for dry-run conversion: "
            f"{status}"
        )


def prepare_hf_mteb_qrels_source(
    output_dir: str | Path,
    *,
    dataset: str = MEMBENCH_HF_DATASET,
    subset: str = "single_hop",
    revision: str,
    include_top_ranked: bool = False,
    split: str | None = None,
    loader: HfDatasetLoader | None = None,
    source_host: str | None = None,
    source_url: str | None = None,
    declared_license: str | None = None,
    license_source: str | None = None,
    license_source_url: str | None = None,
    citation_targets: Iterable[str] | None = None,
    third_party_notice_file: str | None = None,
    redistribution_status: str | None = None,
) -> PreparedMtebSource:
    """Prepare local-only JSONL files from Hugging Face MTEB MemBench configs.

    This helper only writes raw local source files and a conservative source
    manifest. It never writes generated fixture packs.
    """

    if not _is_pinned_revision(revision):
        raise MembenchConversionError(
            "MemBench Hugging Face preparation requires --revision to be pinned "
            "to an immutable 40-character commit SHA"
        )

    target = Path(output_dir)
    _reject_memory_eval_fixture_output(target)
    config_names = _hf_mteb_config_names(
        subset, include_top_ranked=include_top_ranked
    )
    loader_fn = loader or _default_hf_dataset_loader
    records_by_key = {
        key: _load_hf_config_records(
            loader=loader_fn,
            dataset=dataset,
            config_name=config_name,
            revision=revision,
            split=split,
        )
        for key, config_name in config_names.items()
    }

    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "corpus": target / "corpus.jsonl",
        "queries": target / "queries.jsonl",
        "qrels": target / "qrels.jsonl",
    }
    if include_top_ranked:
        paths["top_ranked"] = target / "top_ranked.jsonl"
    for key, path in paths.items():
        _write_jsonl_records(path, records_by_key[key])

    manifest = audit_mteb_source_manifest(
        target,
        source_dataset=dataset,
        source_host=source_host,
        source_url=source_url or _hf_dataset_url(dataset),
        source_revision=revision,
        source_subset=subset,
        declared_license=declared_license,
        license_source=license_source,
        license_source_url=license_source_url,
        citation_targets=citation_targets,
        third_party_notice_file=third_party_notice_file,
        redistribution_status=redistribution_status or "private_only",
    )
    manifest["hf_mteb_export"] = {
        "dataset": dataset,
        "subset": subset,
        "revision": revision,
        "split": split or "auto",
        "config_names": config_names,
        "include_top_ranked": include_top_ranked,
        "raw_source_policy": "local_only_no_vendor",
        "writes_generated_fixtures": False,
    }
    _refresh_source_manifest_hash(manifest)
    manifest_path = target / "source_manifest.json"
    write_json_artifact(manifest_path, manifest)

    return PreparedMtebSource(
        source_dir=target,
        corpus_path=paths["corpus"],
        queries_path=paths["queries"],
        qrels_path=paths["qrels"],
        top_ranked_path=paths.get("top_ranked"),
        manifest_path=manifest_path,
    )


def convert_mteb_qrels_dry_run(
    source_dir: str | Path,
    *,
    source_manifest: Mapping[str, Any] | None = None,
    manifest_path: str | Path | None = None,
    source_revision: str | None = None,
    source_subset: str | Iterable[str] | None = None,
    max_queries: int | None = None,
    seed: int = 12345,
    corpus_sample_policy: str = "full",
    max_corpus_docs: int | None = None,
) -> dict[str, Any]:
    """Convert local MTEB/Hugging Face-style MemBench qrels to a dry-run report."""

    sample_policy = _validate_corpus_sample_policy(corpus_sample_policy)
    if sample_policy == "full":
        max_corpus_docs = None
    elif max_corpus_docs is None or max_corpus_docs <= 0:
        raise MembenchConversionError(
            "--max-corpus-docs must be positive when corpus sampling is enabled"
        )

    root = Path(source_dir)
    manifest = dict(
        source_manifest
        or audit_mteb_source_manifest(
            root,
            manifest_path=manifest_path,
            source_revision=source_revision,
            source_subset=source_subset,
        )
    )
    source_audit_report = validate_mteb_source_manifest(manifest)
    _raise_if_source_audit_blocks_conversion(source_audit_report)
    source = _find_source_files(root, manifest)
    corpus_records, duplicate_doc_ids = _load_corpus(source.corpus_path)
    queries = _load_queries(source.queries_path)
    qrels = _load_qrels(source.qrels_path)

    skipped_examples: list[dict[str, Any]] = []
    fixture_previews = []
    leakage_results = []
    selected_count = 0
    grouped_qrels = _group_qrels(qrels)
    full_doc_ids = [str(record["source_doc_id"]) for record in corpus_records]
    corpus_by_doc_id = _corpus_by_doc_id(corpus_records)
    duplicate_doc_ids = set(duplicate_doc_ids)
    effective_corpus_counts = []
    sampling_rejections = 0

    for query_id in sorted(grouped_qrels):
        if max_queries is not None and selected_count >= max_queries:
            break
        query = queries.get(query_id)
        query_qrels = grouped_qrels[query_id]
        selected_doc_ids = _selected_corpus_doc_ids(
            full_doc_ids=full_doc_ids,
            query_id=query_id,
            query_qrels=query_qrels,
            policy=sample_policy,
            max_corpus_docs=max_corpus_docs,
            seed=seed,
        )
        selected_corpus_records = [
            corpus_by_doc_id[doc_id]
            for doc_id in selected_doc_ids
            if doc_id in corpus_by_doc_id
        ]
        if sample_policy != "full" and len(selected_corpus_records) < len(selected_doc_ids):
            sampling_rejections += 1
        corpus_manifest, doc_to_experience = _build_corpus_manifest(
            selected_corpus_records, manifest=manifest
        )
        rejection = _query_rejection(
            query_id=query_id,
            query=query,
            query_qrels=query_qrels,
            doc_to_experience=doc_to_experience,
            duplicate_doc_ids=duplicate_doc_ids,
        )
        if rejection:
            skipped_examples.append(rejection)
            continue

        source_fixture_base = _fixture_base(
            corpus_records=selected_corpus_records,
            corpus_manifest=corpus_manifest,
            source=source,
            manifest=manifest,
        )
        fixture = deepcopy(source_fixture_base)
        request_index = selected_count + 1
        request, source_qrels = _request_for_query(
            request_index=request_index,
            query_id=query_id,
            query=query or {},
            query_qrels=query_qrels,
            corpus_manifest=corpus_manifest,
            doc_to_experience=doc_to_experience,
        )
        request["gold"]["source_qrels"] = source_qrels
        request["gold"]["corpus_sampling"] = _corpus_sampling_report(
            policy=sample_policy,
            max_corpus_docs=max_corpus_docs,
            effective_corpus_docs=len(selected_corpus_records),
            total_corpus_docs=len(corpus_records),
            query_qrels=query_qrels,
            selected_doc_ids=selected_doc_ids,
        )
        fixture["requests"] = [request]
        fixture["operation_sequence"] = [
            {
                "type": "ingest",
                "experience_id": item["experience_id"],
                "ingest_order": item["ingest_order"],
            }
            for item in fixture["experiences"]
        ]
        fixture["operation_sequence"].append(
            {
                "type": "request",
                "request_id": request["request_id"],
                "after_ingest_order": len(fixture["experiences"]),
            }
        )

        views = split_fixture(fixture, fixture_ordinal=request_index, seed=seed)
        leakage = find_membench_adapter_leakage(views.adapter_view)
        leakage_results.append(
            {
                "fixture_id": fixture["fixture_id"],
                "adapter_fixture_id": views.adapter_fixture_id,
                "failure_count": len(leakage),
                "failures": leakage,
            }
        )
        fixture_previews.append(
            {
                "fixture_id": fixture["fixture_id"],
                "adapter_fixture_id": views.adapter_fixture_id,
                "query_id_hash": stable_hash(query_id),
                "source_fixture_experience_namespace": "exp_src_*",
                "adapter_view": views.adapter_view,
                "scorer_view": views.scorer_view,
                "fixture_public_hash": views.fixture_public_hash,
                "fixture_gold_hash": views.fixture_gold_hash,
                "fixture_full_hash": views.fixture_full_hash,
                "label_leakage_blocked_tokens": deepcopy(
                    fixture.get("label_leakage_blocked_tokens") or []
                ),
                "hash_sensitivity": _hash_sensitivity(
                    fixture, fixture_ordinal=request_index, seed=seed
                ),
                "leakage_failure_count": len(leakage),
            }
        )
        selected_count += 1
        effective_corpus_counts.append(len(selected_corpus_records))

    report = {
        "schema_version": DRY_RUN_SCHEMA_VERSION,
        "converter": {
            "converter_id": CONVERTER_ID,
            "converter_version": CONVERTER_VERSION,
        },
        "source_manifest": manifest,
        "source_audit_report": source_audit_report,
        "source_files": _source_file_manifest(source),
        "seed": seed,
        "conversion_manifest_hash": stable_hash(
            {
                "converter_id": CONVERTER_ID,
                "converter_version": CONVERTER_VERSION,
                "source_manifest_hash": manifest.get("source_manifest_hash"),
                "source_files": _source_file_manifest(source),
            }
        ),
        "candidate_counts": {
            "corpus_documents": len(corpus_records),
            "effective_corpus_documents_min": min(effective_corpus_counts)
            if effective_corpus_counts
            else 0,
            "effective_corpus_documents_max": max(effective_corpus_counts)
            if effective_corpus_counts
            else 0,
            "queries": len(queries),
            "qrel_rows": len(qrels),
            "grouped_qrel_queries": len(grouped_qrels),
            "selected_fixture_previews": len(fixture_previews),
            "skipped_examples": len(skipped_examples),
            "duplicate_doc_ids": len(duplicate_doc_ids),
            "sampling_rejections": sampling_rejections,
        },
        "corpus_sampling": {
            "policy": sample_policy,
            "max_corpus_docs": max_corpus_docs,
            "seed": seed,
            "full_corpus_documents": len(corpus_records),
            "effective_corpus_documents": {
                "min": min(effective_corpus_counts) if effective_corpus_counts else 0,
                "max": max(effective_corpus_counts) if effective_corpus_counts else 0,
            },
        },
        "qrel_mapping": {
            "success_count": len(fixture_previews),
            "skipped_count": len(skipped_examples),
            "duplicate_doc_ids": sorted(duplicate_doc_ids),
        },
        "skipped_examples": skipped_examples,
        "label_like_keys_found": _label_like_keys(
            corpus_records, queries.values(), qrels
        ),
        "label_like_keys_removed_from_adapter_view": sorted(
            MEMBENCH_PRIVATE_STRUCTURAL_KEYS
        ),
        "scorer_only_fields_removed_from_adapter_view": SCORER_ONLY_FIELD_PATHS,
        "leakage_checks": leakage_results,
        "adapter_view_check_summary": _adapter_view_check_summary(leakage_results),
        "category_distribution": {
            str(manifest.get("source_subset") or "unknown"): len(fixture_previews)
        },
        "estimated_budgets": {
            "experience_items_per_fixture": {
                "min": min(effective_corpus_counts) if effective_corpus_counts else 0,
                "max": max(effective_corpus_counts) if effective_corpus_counts else 0,
            },
            "default_k": 5,
            "max_evidence_items": 5,
        },
        "fixture_previews": fixture_previews,
        "commit_policy": {
            "raw_source_committed": False,
            "generated_fixture_pack_committed": False,
            "phase_c_generated_fixture_commit_allowed": source_audit_report[
                "phase_c_commit_preconditions"
            ]["generated_fixture_commit_allowed"],
            "phase_c_status": source_audit_report["phase_c_commit_preconditions"][
                "status"
            ],
            "redistribution_status": source_audit_report["redistribution_status"],
            "dry_run_artifact_policy": "local_only_unless_source_audit_commit_allowed",
        },
    }
    report["dry_run_hash"] = stable_hash(
        {key: value for key, value in report.items() if key != "dry_run_hash"}
    )
    return report


def build_ephemeral_fixtures_from_dry_run(
    dry_run_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Rebuild temporary memory_eval fixture objects from dry-run previews.

    The returned fixtures are in-memory source fixture objects with internal
    `exp_src_*` evidence IDs restored from the scorer view. They are suitable
    for `run_fixture()` and intentionally do not write fixture packs.
    """

    return [
        _fixture_from_dry_run_preview(preview)
        for preview in dry_run_report.get("fixture_previews") or []
    ]


def build_typed_cards_ephemeral_fixtures_from_dry_run(
    dry_run_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Rebuild in-memory dry-run fixtures with typed-card lifecycle setup.

    TypedCardsMemoryEvalAdapter intentionally keeps plain ingested experiences
    as proposals until a public lifecycle mutation commits them. The added
    `seed_eval` mutations go through the neutral adapter boundary and are never
    written as a committed fixture pack.
    """

    return [
        _with_typed_cards_lifecycle_setup(fixture)
        for fixture in build_ephemeral_fixtures_from_dry_run(dry_run_report)
    ]


def _validate_typed_cards_extractor_mode(value: str) -> str:
    mode = str(value or "deterministic_replay").strip() or "deterministic_replay"
    if mode not in TYPED_CARDS_EXTRACTOR_MODES:
        raise MembenchConversionError(
            "typed cards extractor mode must be one of "
            + ", ".join(TYPED_CARDS_EXTRACTOR_MODES)
        )
    return mode


def _empty_validation_result_summary() -> dict[str, Any]:
    return {
        "example_count": 0,
        "status_counts": {},
        "passed": None,
        "hash_mismatch_count": 0,
        "adapter_view_leakage_failure_count": 0,
    }


def validate_mteb_qrels_dry_run(
    dry_run_report: Mapping[str, Any],
    *,
    seed: int | None = None,
    run_broken_controls: bool = True,
    include_typed_cards: bool = False,
    typed_cards_extractor_mode: str = "deterministic_replay",
    allow_live_model_tests: bool = False,
    typed_cards_summary_search_backend: str = "direct_scan_lexical",
    typed_cards_embedding_provider: str = DEFAULT_TYPED_CARDS_EMBEDDING_PROVIDER,
    typed_cards_embedding_model: str = DEFAULT_TYPED_CARDS_EMBEDDING_MODEL,
    typed_cards_live_backend: str = DEFAULT_TYPED_CARDS_LIVE_BACKEND,
    typed_cards_live_model: str = DEFAULT_TYPED_CARDS_LIVE_MODEL,
    typed_cards_live_auth_json: str | Path = DEFAULT_TYPED_CARDS_LIVE_AUTH_JSON,
    typed_cards_live_call_interface: str = DEFAULT_TYPED_CARDS_LIVE_CALL_INTERFACE,
    typed_cards_live_timeout: int = DEFAULT_TYPED_CARDS_LIVE_TIMEOUT,
    typed_cards_live_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Validate dry-run selected previews with in-memory memory_eval fixtures."""

    typed_cards_extractor_mode = _validate_typed_cards_extractor_mode(
        typed_cards_extractor_mode
    )
    validation_seed = _validation_seed(dry_run_report, explicit_seed=seed)
    previews = list(dry_run_report.get("fixture_previews") or [])
    fixtures = build_ephemeral_fixtures_from_dry_run(dry_run_report)
    reference_results = []
    negative_control_results = []
    typed_cards_results = []
    typed_cards_run = False
    typed_cards_not_run_reason = "not requested; pass --include-typed-cards"
    typed_cards_artifact_output_dir: str | None = None

    for index, (preview, fixture) in enumerate(zip(previews, fixtures), start=1):
        fixture_ordinal = _preview_fixture_ordinal(preview, default=index)
        views = split_fixture(
            fixture, fixture_ordinal=fixture_ordinal, seed=validation_seed
        )
        leakage = find_membench_adapter_leakage(views.adapter_view)
        hash_match = {
            "fixture_public_hash_matches_preview": views.fixture_public_hash
            == preview.get("fixture_public_hash"),
            "fixture_gold_hash_matches_preview": views.fixture_gold_hash
            == preview.get("fixture_gold_hash"),
            "fixture_full_hash_matches_preview": views.fixture_full_hash
            == preview.get("fixture_full_hash"),
        }

        reference_artifact = run_fixture(
            fixture,
            _qrels_oracle_adapter_for_views(views),
            seed=validation_seed,
            fixture_ordinal=fixture_ordinal,
            run_id=f"run_membench_reference_{fixture_ordinal:06d}",
            created_at=DEFAULT_VALIDATION_CREATED_AT,
        )
        reference_results.append(
            {
                **_run_validation_summary(
                    artifact=reference_artifact,
                    preview=preview,
                    fixture_ordinal=fixture_ordinal,
                ),
                "hash_match": hash_match,
                "adapter_view_leakage_failure_count": len(leakage),
                "adapter_view_leakage_failures": leakage,
            }
        )

        if run_broken_controls:
            for control in _applicable_negative_controls(fixture):
                artifact = run_fixture(
                    fixture,
                    control["adapter_factory"](),
                    seed=validation_seed,
                    fixture_ordinal=fixture_ordinal,
                    run_id=(
                        f"run_membench_{control['control_id']}_{fixture_ordinal:06d}"
                    ),
                    created_at=DEFAULT_VALIDATION_CREATED_AT,
                )
                negative_control_results.append(
                    _negative_control_summary(
                        artifact=artifact,
                        preview=preview,
                        fixture_ordinal=fixture_ordinal,
                        control=control,
                    )
                )

    if include_typed_cards and typed_cards_extractor_mode == "live_model":
        if allow_live_model_tests:
            live_output_dir = Path(
                typed_cards_live_output_dir or DEFAULT_TYPED_CARDS_LIVE_OUTPUT_DIR
            )
            typed_cards_artifact_output_dir = str(live_output_dir)
            typed_cards_run = True
            typed_cards_not_run_reason = None
            typed_cards_results = _typed_cards_live_validation_results(
                previews=previews,
                fixtures=fixtures,
                validation_seed=validation_seed,
                summary_search_backend=typed_cards_summary_search_backend,
                embedding_provider=typed_cards_embedding_provider,
                embedding_model_id=typed_cards_embedding_model,
                backend=typed_cards_live_backend,
                model=typed_cards_live_model,
                auth_json=typed_cards_live_auth_json,
                call_interface=typed_cards_live_call_interface,
                timeout=typed_cards_live_timeout,
                output_dir=live_output_dir,
            )
        else:
            typed_cards_not_run_reason = (
                "live model tests require --allow-live-model-tests"
            )
    elif include_typed_cards:
        typed_cards_run = True
        typed_cards_not_run_reason = None
        typed_cards_results = _typed_cards_validation_results(
            previews=previews,
            fixtures=fixtures,
            validation_seed=validation_seed,
            summary_search_backend=typed_cards_summary_search_backend,
            embedding_provider=typed_cards_embedding_provider,
            embedding_model_id=typed_cards_embedding_model,
        )

    report = {
        "schema_version": DRY_RUN_VALIDATION_SCHEMA_VERSION,
        "validation_target": "membench_mteb_qrels_dry_run_previews",
        "source_dry_run_schema_version": dry_run_report.get("schema_version"),
        "source_dry_run_hash": dry_run_report.get("dry_run_hash"),
        "converter": dict(dry_run_report.get("converter") or {}),
        "seed": validation_seed,
        "created_at": DEFAULT_VALIDATION_CREATED_AT,
        "ephemeral_fixture_policy": {
            "storage": "in_memory_only",
            "writes_fixture_pack": False,
            "fixtures_memory_eval_write_allowed": False,
            "raw_source_committed": False,
            "generated_fixture_pack_committed": False,
            "typed_cards_lifecycle_setup_storage": "in_memory_only",
        },
        "selected_fixture_count": len(fixtures),
        "reference_adapter": {
            "adapter_id": "memory_eval_reference_p1",
            "result_summary": _validation_result_summary(reference_results),
            "results": reference_results,
        },
        "typed_cards_adapter": {
            "run": typed_cards_run,
            "gating": typed_cards_extractor_mode != "live_model",
            "adapter_id": "mew_typed_cards_memory_eval",
            "extractor_mode": typed_cards_extractor_mode,
            "live_model_extraction": typed_cards_extractor_mode == "live_model",
            "live_model_tests_allowed": bool(allow_live_model_tests),
            "live_model_backend": typed_cards_live_backend
            if typed_cards_extractor_mode == "live_model"
            else None,
            "live_model": typed_cards_live_model
            if typed_cards_extractor_mode == "live_model"
            else None,
            "live_call_interface": typed_cards_live_call_interface
            if typed_cards_extractor_mode == "live_model"
            else None,
            "summary_search_backend": typed_cards_summary_search_backend,
            "embedding_provider": typed_cards_embedding_provider
            if typed_cards_summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None,
            "embedding_model_id": typed_cards_embedding_model
            if typed_cards_summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None,
            "artifact_output_dir": typed_cards_artifact_output_dir,
            "setup_policy": "public_seed_eval_lifecycle_after_each_ingest",
            "result_summary": _validation_result_summary(typed_cards_results)
            if typed_cards_run
            else _empty_validation_result_summary(),
            "results": typed_cards_results,
            "not_run_reason": typed_cards_not_run_reason,
        },
        "negative_controls": {
            "run": bool(run_broken_controls),
            "result_summary": _negative_control_result_summary(
                negative_control_results
            ),
            "results": negative_control_results,
            "not_run": _negative_controls_not_run_notes(),
        },
    }
    report["validation_status"] = _validation_status(report)
    report["validation_hash"] = stable_hash(
        {key: value for key, value in report.items() if key != "validation_hash"}
    )
    return report


def run_profile(
    profile_name: str,
    *,
    work_dir: str | Path = "tmp/membench-profiles",
    revision: str | None = None,
    clean: bool = False,
    loader: HfDatasetLoader | None = None,
    typed_cards_extractor_mode: str = "deterministic_replay",
    allow_live_model_tests: bool = False,
    typed_cards_summary_search_backend: str = "direct_scan_lexical",
    typed_cards_embedding_provider: str = DEFAULT_TYPED_CARDS_EMBEDDING_PROVIDER,
    typed_cards_embedding_model: str = DEFAULT_TYPED_CARDS_EMBEDDING_MODEL,
    typed_cards_live_backend: str = DEFAULT_TYPED_CARDS_LIVE_BACKEND,
    typed_cards_live_model: str = DEFAULT_TYPED_CARDS_LIVE_MODEL,
    typed_cards_live_auth_json: str | Path = DEFAULT_TYPED_CARDS_LIVE_AUTH_JSON,
    typed_cards_live_call_interface: str = DEFAULT_TYPED_CARDS_LIVE_CALL_INTERFACE,
    typed_cards_live_timeout: int = DEFAULT_TYPED_CARDS_LIVE_TIMEOUT,
    typed_cards_live_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    typed_cards_extractor_mode = _validate_typed_cards_extractor_mode(
        typed_cards_extractor_mode
    )
    if profile_name not in PROFILE_NAMES:
        raise MembenchConversionError(
            f"unknown MemBench profile {profile_name!r}; available profiles: "
            + ", ".join(PROFILE_NAMES)
        )
    profile_config = PROFILE_CONFIGS[profile_name]
    source_revision = revision or MEMBENCH_HF_PROFILE_REVISION
    if not _is_pinned_revision(source_revision):
        raise MembenchConversionError(
            "MemBench profile requires a pinned 40-character dataset revision"
        )

    profile_dir = Path(work_dir) / profile_name
    source_dir = profile_dir / "source"
    dry_run_path = profile_dir / "dry_run.json"
    validation_path = profile_dir / "validation.json"
    report_path = profile_dir / "profile_report.json"
    if clean and profile_dir.exists():
        shutil.rmtree(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    phases: dict[str, Any] = {}
    prepared = prepare_hf_mteb_qrels_source(
        source_dir,
        dataset=MEMBENCH_HF_DATASET,
        subset=str(profile_config["subset"]),
        revision=source_revision,
        loader=loader,
        declared_license="mit",
        license_source="Hugging Face dataset card",
        license_source_url=MEMBENCH_HF_DATASET_URL,
        citation_targets=["mteb/MemBench dataset card", "MTEB"],
    )
    phases["setup.prepare"] = {
        "status": "passed",
        "source_dir": str(prepared.source_dir),
        "source_manifest": str(prepared.manifest_path),
        "source_files": _source_file_manifest(prepared),
        "raw_source_committed": False,
        "generated_fixture_pack_committed": False,
    }

    source_gate = validate_mteb_source_manifest(_load_json_object(prepared.manifest_path))
    phases["setup.source_gate"] = {
        "status": source_gate["phase_c_commit_preconditions"]["status"],
        "generated_fixture_commit_allowed": source_gate[
            "phase_c_commit_preconditions"
        ]["generated_fixture_commit_allowed"],
        "local_evaluation_allowed": source_gate["phase_c_commit_preconditions"][
            "local_evaluation_allowed"
        ],
        "raw_source_commit_allowed": source_gate["phase_c_commit_preconditions"][
            "raw_source_commit_allowed"
        ],
        "source_audit_report_hash": source_gate["source_audit_report_hash"],
    }

    max_queries = profile_config["max_queries"]
    max_corpus_docs = profile_config["max_corpus_docs"]
    dry_run = convert_mteb_qrels_dry_run(
        prepared.source_dir,
        manifest_path=prepared.manifest_path,
        max_queries=int(max_queries) if max_queries is not None else None,
        corpus_sample_policy=str(profile_config["corpus_sample_policy"]),
        max_corpus_docs=int(max_corpus_docs) if max_corpus_docs is not None else None,
    )
    write_json_artifact(dry_run_path, dry_run)
    phases["setup.dry_run"] = {
        "status": "passed"
        if dry_run["adapter_view_check_summary"]["passed"]
        and dry_run["qrel_mapping"]["success_count"] > 0
        else "failed",
        "artifact": str(dry_run_path),
        "dry_run_hash": dry_run["dry_run_hash"],
        "candidate_counts": dry_run["candidate_counts"],
        "corpus_sampling": dry_run["corpus_sampling"],
        "adapter_view_check_summary": dry_run["adapter_view_check_summary"],
    }

    validation = validate_mteb_qrels_dry_run(
        dry_run,
        include_typed_cards=bool(profile_config["include_typed_cards"]),
        typed_cards_extractor_mode=typed_cards_extractor_mode,
        allow_live_model_tests=allow_live_model_tests,
        typed_cards_summary_search_backend=typed_cards_summary_search_backend,
        typed_cards_embedding_provider=typed_cards_embedding_provider,
        typed_cards_embedding_model=typed_cards_embedding_model,
        typed_cards_live_backend=typed_cards_live_backend,
        typed_cards_live_model=typed_cards_live_model,
        typed_cards_live_auth_json=typed_cards_live_auth_json,
        typed_cards_live_call_interface=typed_cards_live_call_interface,
        typed_cards_live_timeout=typed_cards_live_timeout,
        typed_cards_live_output_dir=typed_cards_live_output_dir,
    )
    write_json_artifact(validation_path, validation)
    phases["run.validation"] = {
        "status": validation["validation_status"],
        "artifact": str(validation_path),
        "validation_hash": validation["validation_hash"],
        "qrels_oracle": validation["reference_adapter"]["result_summary"],
        "typed_cards": validation["typed_cards_adapter"]["result_summary"],
        "negative_controls": validation["negative_controls"]["result_summary"],
    }
    report = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profile": profile_name,
        "profile_config": {
            "dataset": MEMBENCH_HF_DATASET,
            "subset": profile_config["subset"],
            "revision": source_revision,
            "max_queries": profile_config["max_queries"],
            "corpus_sample_policy": profile_config["corpus_sample_policy"],
            "max_corpus_docs": profile_config["max_corpus_docs"],
            "include_typed_cards": profile_config["include_typed_cards"],
        },
        "typed_cards_adapter_config": {
            "extractor_mode": typed_cards_extractor_mode,
            "live_model_extraction": typed_cards_extractor_mode == "live_model",
            "live_model_tests_allowed": bool(allow_live_model_tests),
            "live_model_backend": typed_cards_live_backend
            if typed_cards_extractor_mode == "live_model"
            else None,
            "live_model": typed_cards_live_model
            if typed_cards_extractor_mode == "live_model"
            else None,
            "summary_search_backend": typed_cards_summary_search_backend,
            "embedding_provider": typed_cards_embedding_provider
            if typed_cards_summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None,
            "embedding_model_id": typed_cards_embedding_model
            if typed_cards_summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None,
            "artifact_output_dir": validation["typed_cards_adapter"].get(
                "artifact_output_dir"
            ),
        },
        "artifacts": {
            "source_dir": str(prepared.source_dir),
            "source_manifest": str(prepared.manifest_path),
            "dry_run": str(dry_run_path),
            "validation": str(validation_path),
            "profile_report": str(report_path),
        },
        "phases": phases,
        "summary": _profile_summary(phases),
        "commit_policy": {
            "raw_source_committed": False,
            "generated_fixture_pack_committed": False,
            "profile_artifacts_local_only": True,
        },
    }
    report["profile_hash"] = stable_hash(
        {key: value for key, value in report.items() if key != "profile_hash"}
    )
    write_json_artifact(report_path, report)
    return report


def find_membench_adapter_leakage(
    adapter_view: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return converter-specific adapter-view leakage findings."""

    failures = []
    for path, key, value in _walk_with_keys(adapter_view):
        normalized_key = _normalize_key(key)
        if normalized_key in MEMBENCH_PRIVATE_STRUCTURAL_KEYS:
            failures.append(
                _leak_failure(
                    path=path,
                    token=normalized_key,
                    message=f"Adapter view contains MemBench scorer-only key {key!r}.",
                )
            )
        if isinstance(value, str):
            normalized_value = value.lower()
            for token in sorted(MEMBENCH_PRIVATE_VALUE_TOKENS, key=len, reverse=True):
                if token in normalized_value:
                    failures.append(
                        _leak_failure(
                            path=path,
                            token=token,
                            message=f"Adapter view contains MemBench scorer-only token {token!r}.",
                        )
                    )
                    break
    return failures


def write_json_artifact(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _add_typed_cards_backend_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--typed-cards-extractor-mode",
        choices=TYPED_CARDS_EXTRACTOR_MODES,
        default="deterministic_replay",
        help=(
            "Extractor mode for typed-card validation. live_model is opt-in "
            "and also requires --allow-live-model-tests."
        ),
    )
    parser.add_argument(
        "--allow-live-model-tests",
        action="store_true",
        help=(
            "Permit non-gating live model calls for typed-card validation. "
            "Hermetic CI should omit this flag."
        ),
    )
    parser.add_argument(
        "--typed-cards-live-backend",
        default=DEFAULT_TYPED_CARDS_LIVE_BACKEND,
        help="Live typed-card extractor backend.",
    )
    parser.add_argument(
        "--typed-cards-live-model",
        default=DEFAULT_TYPED_CARDS_LIVE_MODEL,
        help="Live typed-card extractor model.",
    )
    parser.add_argument(
        "--typed-cards-live-auth-json",
        default=str(DEFAULT_TYPED_CARDS_LIVE_AUTH_JSON),
        help="Auth JSON path for live typed-card extractor calls.",
    )
    parser.add_argument(
        "--typed-cards-live-call-interface",
        choices=("call_model_structured_json", "call_model_json"),
        default=DEFAULT_TYPED_CARDS_LIVE_CALL_INTERFACE,
        help="Call interface for live typed-card extractor calls.",
    )
    parser.add_argument(
        "--typed-cards-live-timeout",
        type=int,
        default=DEFAULT_TYPED_CARDS_LIVE_TIMEOUT,
        help="Per-call timeout for live typed-card extractor calls.",
    )
    parser.add_argument(
        "--typed-cards-live-output-dir",
        default=None,
        help="Directory for non-gating live typed-card artifact output.",
    )
    parser.add_argument(
        "--typed-cards-summary-search-backend",
        choices=TYPED_CARDS_SUMMARY_SEARCH_BACKENDS,
        default="direct_scan_lexical",
        help=(
            "Typed-card summary search backend used when --include-typed-cards "
            "or a typed-card profile is enabled."
        ),
    )
    parser.add_argument(
        "--typed-cards-embedding-provider",
        default=DEFAULT_TYPED_CARDS_EMBEDDING_PROVIDER,
        help="Embedding provider for vector/hybrid typed-card summary search.",
    )
    parser.add_argument(
        "--typed-cards-embedding-model",
        default=DEFAULT_TYPED_CARDS_EMBEDDING_MODEL,
        help="Embedding model for vector/hybrid typed-card summary search.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    audit_parser = subcommands.add_parser("audit-source")
    audit_parser.add_argument("source_dir")
    audit_parser.add_argument("--manifest")
    audit_parser.add_argument("--source-host")
    audit_parser.add_argument("--source-url")
    audit_parser.add_argument("--source-revision")
    audit_parser.add_argument("--source-subset", action="append")
    audit_parser.add_argument("--declared-license")
    audit_parser.add_argument("--license-source")
    audit_parser.add_argument("--license-source-url")
    audit_parser.add_argument("--citation-target", action="append")
    audit_parser.add_argument("--third-party-notice-file")
    audit_parser.add_argument(
        "--redistribution-status", choices=REDISTRIBUTION_STATUSES
    )
    audit_parser.add_argument(
        "--redistribution-review-approved",
        action="store_true",
        help=(
            "Record explicit reviewer approval for generated fixture commit "
            "readiness; raw source vendoring remains disallowed."
        ),
    )
    audit_parser.add_argument("--redistribution-reviewer")
    audit_parser.add_argument("--redistribution-reviewed-at")
    audit_parser.add_argument("--redistribution-decision-basis")
    audit_parser.add_argument(
        "--redistribution-review-scope",
        default=None,
        choices=[REDISTRIBUTION_REVIEW_SCOPE],
    )
    audit_parser.add_argument("--output", required=True)

    source_report_parser = subcommands.add_parser("validate-source-manifest")
    source_report_parser.add_argument("source_manifest")
    source_report_parser.add_argument("--require-commit-allowed", action="store_true")
    source_report_parser.add_argument("--output")

    dry_run_parser = subcommands.add_parser("dry-run-mteb-qrels")
    dry_run_parser.add_argument("source_dir")
    dry_run_parser.add_argument("--manifest")
    dry_run_parser.add_argument("--source-revision")
    dry_run_parser.add_argument("--source-subset", action="append")
    dry_run_parser.add_argument("--max-queries", type=int)
    dry_run_parser.add_argument(
        "--corpus-sample-policy",
        choices=CORPUS_SAMPLE_POLICIES,
        default="full",
    )
    dry_run_parser.add_argument("--max-corpus-docs", type=int)
    dry_run_parser.add_argument("--seed", type=int, default=12345)
    dry_run_parser.add_argument("--output", required=True)

    prepare_parser = subcommands.add_parser("prepare-hf-mteb-qrels")
    prepare_parser.add_argument("output_dir")
    prepare_parser.add_argument("--dataset", default=MEMBENCH_HF_DATASET)
    prepare_parser.add_argument("--subset", default="single_hop")
    prepare_parser.add_argument("--revision", required=True)
    prepare_parser.add_argument("--split")
    prepare_parser.add_argument("--include-top-ranked", action="store_true")
    prepare_parser.add_argument("--source-host")
    prepare_parser.add_argument("--source-url")
    prepare_parser.add_argument("--declared-license")
    prepare_parser.add_argument("--license-source")
    prepare_parser.add_argument("--license-source-url")
    prepare_parser.add_argument("--citation-target", action="append")
    prepare_parser.add_argument("--third-party-notice-file")
    prepare_parser.add_argument(
        "--redistribution-status",
        choices=REDISTRIBUTION_STATUSES,
        default="private_only",
    )

    validate_report_parser = subcommands.add_parser("validate-dry-run-report")
    validate_report_parser.add_argument("dry_run_report")
    validate_report_parser.add_argument("--seed", type=int)
    validate_report_parser.add_argument("--include-typed-cards", action="store_true")
    _add_typed_cards_backend_args(validate_report_parser)
    validate_report_parser.add_argument("--output")

    validate_parser = subcommands.add_parser("validate-dry-run-mteb-qrels")
    validate_parser.add_argument("source_dir")
    validate_parser.add_argument("--manifest")
    validate_parser.add_argument("--source-revision")
    validate_parser.add_argument("--source-subset", action="append")
    validate_parser.add_argument("--max-queries", type=int)
    validate_parser.add_argument(
        "--corpus-sample-policy",
        choices=CORPUS_SAMPLE_POLICIES,
        default="full",
    )
    validate_parser.add_argument("--max-corpus-docs", type=int)
    validate_parser.add_argument("--seed", type=int, default=12345)
    validate_parser.add_argument("--include-typed-cards", action="store_true")
    _add_typed_cards_backend_args(validate_parser)
    validate_parser.add_argument("--output")

    profile_parser = subcommands.add_parser("profile")
    profile_parser.add_argument("profile_name", choices=PROFILE_NAMES)
    profile_parser.add_argument("--work-dir", default="tmp/membench-profiles")
    profile_parser.add_argument(
        "--revision",
        default=None,
        help=(
            "Override the profile's pinned Hugging Face dataset commit "
            f"(default: {MEMBENCH_HF_PROFILE_REVISION})."
        ),
    )
    profile_parser.add_argument("--clean", action="store_true")
    _add_typed_cards_backend_args(profile_parser)
    profile_parser.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "audit-source":
        manifest = audit_mteb_source_manifest(
            args.source_dir,
            manifest_path=args.manifest,
            source_host=args.source_host,
            source_url=args.source_url,
            source_revision=args.source_revision,
            source_subset=args.source_subset,
            declared_license=args.declared_license,
            license_source=args.license_source,
            license_source_url=args.license_source_url,
            citation_targets=args.citation_target,
            third_party_notice_file=args.third_party_notice_file,
            redistribution_status=args.redistribution_status,
            redistribution_review_approved=args.redistribution_review_approved
            or None,
            redistribution_reviewer=args.redistribution_reviewer,
            redistribution_reviewed_at=args.redistribution_reviewed_at,
            redistribution_decision_basis=args.redistribution_decision_basis,
            redistribution_review_scope=args.redistribution_review_scope,
        )
        write_json_artifact(args.output, manifest)
        return 0

    if args.command == "validate-source-manifest":
        report = validate_mteb_source_manifest(_load_json_object(args.source_manifest))
        _write_or_print_json(report, args.output)
        preconditions = report["phase_c_commit_preconditions"]
        if args.require_commit_allowed:
            return 0 if preconditions["generated_fixture_commit_allowed"] else 1
        return 0 if preconditions["status"] != "invalid" else 1

    if args.command == "prepare-hf-mteb-qrels":
        try:
            prepared = prepare_hf_mteb_qrels_source(
                args.output_dir,
                dataset=args.dataset,
                subset=args.subset,
                revision=args.revision,
                include_top_ranked=args.include_top_ranked,
                split=args.split,
                source_host=args.source_host,
                source_url=args.source_url,
                declared_license=args.declared_license,
                license_source=args.license_source,
                license_source_url=args.license_source_url,
                citation_targets=args.citation_target,
                third_party_notice_file=args.third_party_notice_file,
                redistribution_status=args.redistribution_status,
            )
        except MembenchConversionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        _write_or_print_json(
            {
                "source_dir": str(prepared.source_dir),
                "source_manifest": str(prepared.manifest_path),
                "source_files": _source_file_manifest(prepared),
                "raw_source_committed": False,
                "generated_fixture_pack_committed": False,
            },
            None,
        )
        return 0

    if args.command == "validate-dry-run-report":
        report = validate_mteb_qrels_dry_run(
            _load_json_object(args.dry_run_report),
            seed=args.seed,
            include_typed_cards=args.include_typed_cards,
            typed_cards_extractor_mode=args.typed_cards_extractor_mode,
            allow_live_model_tests=args.allow_live_model_tests,
            typed_cards_summary_search_backend=(
                args.typed_cards_summary_search_backend
            ),
            typed_cards_embedding_provider=args.typed_cards_embedding_provider,
            typed_cards_embedding_model=args.typed_cards_embedding_model,
            typed_cards_live_backend=args.typed_cards_live_backend,
            typed_cards_live_model=args.typed_cards_live_model,
            typed_cards_live_auth_json=args.typed_cards_live_auth_json,
            typed_cards_live_call_interface=args.typed_cards_live_call_interface,
            typed_cards_live_timeout=args.typed_cards_live_timeout,
            typed_cards_live_output_dir=args.typed_cards_live_output_dir,
        )
        _write_or_print_json(report, args.output)
        return 0 if report["validation_status"] == "passed" else 1

    if args.command == "profile":
        try:
            report = run_profile(
                args.profile_name,
                work_dir=args.work_dir,
                revision=args.revision,
                clean=args.clean,
                typed_cards_extractor_mode=args.typed_cards_extractor_mode,
                allow_live_model_tests=args.allow_live_model_tests,
                typed_cards_summary_search_backend=(
                    args.typed_cards_summary_search_backend
                ),
                typed_cards_embedding_provider=args.typed_cards_embedding_provider,
                typed_cards_embedding_model=args.typed_cards_embedding_model,
                typed_cards_live_backend=args.typed_cards_live_backend,
                typed_cards_live_model=args.typed_cards_live_model,
                typed_cards_live_auth_json=args.typed_cards_live_auth_json,
                typed_cards_live_call_interface=args.typed_cards_live_call_interface,
                typed_cards_live_timeout=args.typed_cards_live_timeout,
                typed_cards_live_output_dir=args.typed_cards_live_output_dir,
            )
        except MembenchConversionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        _write_or_print_json(report, args.output)
        return 0 if report["summary"]["status"] == "passed" else 1

    report = convert_mteb_qrels_dry_run(
        args.source_dir,
        manifest_path=args.manifest,
        source_revision=args.source_revision,
        source_subset=args.source_subset,
        max_queries=args.max_queries,
        corpus_sample_policy=args.corpus_sample_policy,
        max_corpus_docs=args.max_corpus_docs,
        seed=args.seed,
    )
    if args.command == "dry-run-mteb-qrels":
        write_json_artifact(args.output, report)
        return 0

    report = validate_mteb_qrels_dry_run(
        report,
        seed=args.seed,
        include_typed_cards=args.include_typed_cards,
        typed_cards_extractor_mode=args.typed_cards_extractor_mode,
        allow_live_model_tests=args.allow_live_model_tests,
        typed_cards_summary_search_backend=args.typed_cards_summary_search_backend,
        typed_cards_embedding_provider=args.typed_cards_embedding_provider,
        typed_cards_embedding_model=args.typed_cards_embedding_model,
        typed_cards_live_backend=args.typed_cards_live_backend,
        typed_cards_live_model=args.typed_cards_live_model,
        typed_cards_live_auth_json=args.typed_cards_live_auth_json,
        typed_cards_live_call_interface=args.typed_cards_live_call_interface,
        typed_cards_live_timeout=args.typed_cards_live_timeout,
        typed_cards_live_output_dir=args.typed_cards_live_output_dir,
    )
    _write_or_print_json(report, args.output)
    return 0 if report["validation_status"] == "passed" else 1


def _write_or_print_json(value: Mapping[str, Any], output: str | None) -> None:
    if output:
        write_json_artifact(output, value)
        return
    print(json.dumps(value, indent=2, sort_keys=True))


def _profile_summary(phases: Mapping[str, Any]) -> dict[str, Any]:
    source_gate_status = str((phases.get("setup.source_gate") or {}).get("status"))
    dry_run_status = str((phases.get("setup.dry_run") or {}).get("status"))
    validation_status = str((phases.get("run.validation") or {}).get("status"))
    qrels_oracle = (phases.get("run.validation") or {}).get("qrels_oracle") or {}
    typed_cards = (phases.get("run.validation") or {}).get("typed_cards") or {}
    setup_passed = (
        (phases.get("setup.prepare") or {}).get("status") == "passed"
        and source_gate_status in {"private_only", "commit_allowed_ready"}
        and dry_run_status == "passed"
    )
    qrels_oracle_passed = qrels_oracle.get("passed") is True
    typed_cards_passed = typed_cards.get("passed") is True
    status = (
        "passed"
        if setup_passed and validation_status == "passed"
        else "failed"
    )
    return {
        "status": status,
        "setup_passed": setup_passed,
        "source_gate_status": source_gate_status,
        "dry_run_status": dry_run_status,
        "qrels_oracle_passed": qrels_oracle_passed,
        "typed_cards_passed": typed_cards_passed,
        "typed_cards_status_counts": dict(typed_cards.get("status_counts") or {}),
    }


def _fixture_from_dry_run_preview(preview: Mapping[str, Any]) -> dict[str, Any]:
    scorer_view = dict(preview.get("scorer_view") or {})
    adapter_view = dict(preview.get("adapter_view") or {})
    adapter_requests = {
        str(request.get("request_id") or ""): request
        for request in adapter_view.get("requests") or []
    }
    requests = []
    for scorer_request in scorer_view.get("requests") or []:
        adapter_request_id = str(scorer_request.get("adapter_request_id") or "")
        adapter_request = adapter_requests.get(adapter_request_id)
        if adapter_request is None:
            raise MembenchConversionError(
                f"Dry-run preview missing adapter request {adapter_request_id!r}"
            )
        request = {
            key: deepcopy(adapter_request.get(key))
            for key in REQUEST_PUBLIC_FIELD_NAMES
            if key in adapter_request
        }
        request["request_id"] = scorer_request.get("request_id")
        for key in REQUEST_SCORER_FIELD_NAMES:
            if key in scorer_request:
                value = deepcopy(scorer_request.get(key))
                if key == "expected_failure_types" and not value:
                    continue
                request[key] = value
        requests.append(request)

    fixture = {
        "schema_version": scorer_view.get("schema_version") or FIXTURE_SCHEMA_VERSION,
        "fixture_id": scorer_view.get("fixture_id"),
        "fixture_version": scorer_view.get("fixture_version"),
        "fixture_family": scorer_view.get("fixture_family"),
        "phase": scorer_view.get("phase"),
        "evaluation_time": scorer_view.get("evaluation_time"),
        "experiences": deepcopy(scorer_view.get("experiences") or []),
        "mutations": deepcopy(scorer_view.get("mutations") or []),
        "requests": requests,
        "operation_sequence": deepcopy(scorer_view.get("operation_sequence") or []),
    }
    if "label_leakage_blocked_tokens" in preview:
        fixture["label_leakage_blocked_tokens"] = deepcopy(
            preview.get("label_leakage_blocked_tokens") or []
        )
    if "source_benchmark" in scorer_view:
        fixture["source_benchmark"] = deepcopy(scorer_view["source_benchmark"])
    return fixture


def _with_typed_cards_lifecycle_setup(fixture: Mapping[str, Any]) -> dict[str, Any]:
    typed_fixture = deepcopy(fixture)
    setup_mutations = []
    rewritten_sequence = []
    for operation in typed_fixture.get("operation_sequence") or []:
        operation_copy = dict(operation)
        rewritten_sequence.append(operation_copy)
        if operation_copy.get("type") != "ingest":
            continue
        experience_id = str(operation_copy.get("experience_id") or "")
        if not experience_id:
            continue
        op_id = f"typed_cards_seed_{len(setup_mutations) + 1:06d}"
        setup_mutations.append(
            {
                "op_id": op_id,
                "mutation_type": "seed_eval",
                "target_experience_id": experience_id,
                "effective_time": typed_fixture.get("evaluation_time")
                or DEFAULT_EVALUATION_TIME,
                "reason": "typed-card public lifecycle seed",
            }
        )
        rewritten_sequence.append(
            {
                "type": "mutate",
                "op_id": op_id,
                "ingest_order": operation_copy.get("ingest_order"),
            }
        )
    typed_fixture["mutations"] = [
        *setup_mutations,
        *(typed_fixture.get("mutations") or []),
    ]
    typed_fixture["operation_sequence"] = rewritten_sequence
    return typed_fixture


def _preview_fixture_ordinal(preview: Mapping[str, Any], *, default: int) -> int:
    match = re.fullmatch(r"fx_(\d+)", str(preview.get("adapter_fixture_id") or ""))
    return int(match.group(1)) if match else default


def _qrels_oracle_adapter_for_views(views: Any) -> _MembenchQrelsOracleAdapter:
    experience_id_to_adapter = views.id_maps.get("experience_id_to_adapter") or {}
    support_by_request = {}
    for request in views.scorer_view.get("requests") or []:
        adapter_request_id = str(request.get("adapter_request_id") or "")
        relevant_ids = (request.get("gold") or {}).get("relevant_evidence_ids") or []
        support_by_request[adapter_request_id] = [
            experience_id_to_adapter[item]
            for item in relevant_ids
            if item in experience_id_to_adapter
        ]
    return _MembenchQrelsOracleAdapter(support_by_request)


def _typed_cards_validation_results(
    *,
    previews: list[Mapping[str, Any]],
    fixtures: list[Mapping[str, Any]],
    validation_seed: int,
    summary_search_backend: str = "direct_scan_lexical",
    embedding_provider: str = DEFAULT_TYPED_CARDS_EMBEDDING_PROVIDER,
    embedding_model_id: str = DEFAULT_TYPED_CARDS_EMBEDDING_MODEL,
) -> list[dict[str, Any]]:
    try:
        from .adapters.typed_cards import TypedCardsMemoryEvalAdapter
    except Exception as exc:  # pragma: no cover - exercised only in broken installs.
        return [
            _typed_cards_unavailable_summary(
                preview=preview,
                fixture_ordinal=_preview_fixture_ordinal(preview, default=index),
                error=exc,
            )
            for index, preview in enumerate(previews, start=1)
        ]

    results = []
    for index, (preview, fixture) in enumerate(zip(previews, fixtures), start=1):
        fixture_ordinal = _preview_fixture_ordinal(preview, default=index)
        typed_fixture = _with_typed_cards_lifecycle_setup(fixture)
        try:
            source_views = split_fixture(
                fixture, fixture_ordinal=fixture_ordinal, seed=validation_seed
            )
            source_leakage = find_membench_adapter_leakage(source_views.adapter_view)
            typed_views = split_fixture(
                typed_fixture, fixture_ordinal=fixture_ordinal, seed=validation_seed
            )
            typed_leakage = find_membench_adapter_leakage(typed_views.adapter_view)
            artifact = run_fixture(
                typed_fixture,
                TypedCardsMemoryEvalAdapter(
                    extractor_mode="deterministic_replay",
                    summary_search_backend=summary_search_backend,
                    embedding_provider=embedding_provider,
                    embedding_model_id=embedding_model_id,
                ),
                seed=validation_seed,
                fixture_ordinal=fixture_ordinal,
                run_id=f"run_membench_typed_cards_{fixture_ordinal:06d}",
                created_at=DEFAULT_VALIDATION_CREATED_AT,
            )
        except Exception as exc:
            results.append(
                _typed_cards_error_summary(
                    preview=preview,
                    fixture_ordinal=fixture_ordinal,
                    error=exc,
                )
            )
            continue

        summary = _run_validation_summary(
            artifact=artifact,
            preview=preview,
            fixture_ordinal=fixture_ordinal,
        )
        summary["source_hash_match"] = {
            "fixture_public_hash_matches_preview": source_views.fixture_public_hash
            == preview.get("fixture_public_hash"),
            "fixture_gold_hash_matches_preview": source_views.fixture_gold_hash
            == preview.get("fixture_gold_hash"),
            "fixture_full_hash_matches_preview": source_views.fixture_full_hash
            == preview.get("fixture_full_hash"),
        }
        summary["hash_match"] = dict(summary["source_hash_match"])
        summary["source_adapter_view_leakage_failure_count"] = len(source_leakage)
        summary["source_adapter_view_leakage_failures"] = source_leakage
        summary["typed_cards_adapter_view_leakage_failure_count"] = len(typed_leakage)
        summary["typed_cards_adapter_view_leakage_failures"] = typed_leakage
        summary["adapter_view_leakage_failure_count"] = len(typed_leakage)
        summary["adapter_view_leakage_failures"] = typed_leakage
        summary["typed_cards_setup_mutation_count"] = len(
            [
                mutation
                for mutation in typed_fixture.get("mutations") or []
                if mutation.get("mutation_type") == "seed_eval"
            ]
        )
        summary["typed_cards_fixture_hashes"] = {
            "fixture_public_hash": typed_views.fixture_public_hash,
            "fixture_gold_hash": typed_views.fixture_gold_hash,
            "fixture_full_hash": typed_views.fixture_full_hash,
        }
        summary["typed_cards_summary_search_backend"] = summary_search_backend
        summary["typed_cards_embedding_provider"] = (
            embedding_provider
            if summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None
        )
        summary["typed_cards_embedding_model_id"] = (
            embedding_model_id
            if summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None
        )
        if typed_leakage:
            summary["result_status"] = "failed"
            summary["failure_types"] = sorted(
                {*summary["failure_types"], "typed_cards_adapter_view_leakage"}
            )
            summary["failed_gate_ids"] = sorted(
                {*summary["failed_gate_ids"], "no_label_leakage"}
            )
        results.append(summary)
    return results


def _typed_cards_live_validation_results(
    *,
    previews: list[Mapping[str, Any]],
    fixtures: list[Mapping[str, Any]],
    validation_seed: int,
    summary_search_backend: str = "direct_scan_lexical",
    embedding_provider: str = DEFAULT_TYPED_CARDS_EMBEDDING_PROVIDER,
    embedding_model_id: str = DEFAULT_TYPED_CARDS_EMBEDDING_MODEL,
    backend: str = DEFAULT_TYPED_CARDS_LIVE_BACKEND,
    model: str = DEFAULT_TYPED_CARDS_LIVE_MODEL,
    auth_json: str | Path = DEFAULT_TYPED_CARDS_LIVE_AUTH_JSON,
    call_interface: str = DEFAULT_TYPED_CARDS_LIVE_CALL_INTERFACE,
    timeout: int = DEFAULT_TYPED_CARDS_LIVE_TIMEOUT,
    output_dir: str | Path = DEFAULT_TYPED_CARDS_LIVE_OUTPUT_DIR,
) -> list[dict[str, Any]]:
    try:
        from .adapters.typed_cards import TypedCardsMemoryEvalAdapter
    except Exception as exc:  # pragma: no cover - exercised only in broken installs.
        return [
            _typed_cards_unavailable_summary(
                preview=preview,
                fixture_ordinal=_preview_fixture_ordinal(preview, default=index),
                error=exc,
            )
            for index, preview in enumerate(previews, start=1)
        ]

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    auth_path = str(Path(auth_json).expanduser())
    results = []
    for index, (preview, fixture) in enumerate(zip(previews, fixtures), start=1):
        fixture_ordinal = _preview_fixture_ordinal(preview, default=index)
        typed_fixture = _with_typed_cards_lifecycle_setup(fixture)
        artifact_path = target_dir / (
            f"run_membench_live_typed_cards_{fixture_ordinal:06d}.json"
        )
        try:
            source_views = split_fixture(
                fixture, fixture_ordinal=fixture_ordinal, seed=validation_seed
            )
            source_leakage = find_membench_adapter_leakage(source_views.adapter_view)
            typed_views = split_fixture(
                typed_fixture, fixture_ordinal=fixture_ordinal, seed=validation_seed
            )
            typed_leakage = find_membench_adapter_leakage(typed_views.adapter_view)
            artifact = run_fixture(
                typed_fixture,
                TypedCardsMemoryEvalAdapter.live_model(
                    extractor_config={
                        "backend": backend,
                        "model": model,
                        "auth_path": auth_path,
                        "call_interface": call_interface,
                    },
                    timeout=timeout,
                    summary_search_backend=summary_search_backend,
                    embedding_provider=embedding_provider,
                    embedding_model_id=embedding_model_id,
                ),
                seed=validation_seed,
                fixture_ordinal=fixture_ordinal,
                run_id=f"run_membench_live_typed_cards_{fixture_ordinal:06d}",
                created_at=DEFAULT_VALIDATION_CREATED_AT,
            )
            write_json_artifact(artifact_path, artifact)
        except Exception as exc:
            summary = _typed_cards_error_summary(
                preview=preview,
                fixture_ordinal=fixture_ordinal,
                error=exc,
            )
            summary["typed_cards_live_model_backend"] = backend
            summary["typed_cards_live_model"] = model
            summary["typed_cards_live_call_interface"] = call_interface
            summary["typed_cards_live_artifact_path"] = None
            results.append(summary)
            continue

        summary = _run_validation_summary(
            artifact=artifact,
            preview=preview,
            fixture_ordinal=fixture_ordinal,
        )
        summary["source_hash_match"] = {
            "fixture_public_hash_matches_preview": source_views.fixture_public_hash
            == preview.get("fixture_public_hash"),
            "fixture_gold_hash_matches_preview": source_views.fixture_gold_hash
            == preview.get("fixture_gold_hash"),
            "fixture_full_hash_matches_preview": source_views.fixture_full_hash
            == preview.get("fixture_full_hash"),
        }
        summary["hash_match"] = dict(summary["source_hash_match"])
        summary["source_adapter_view_leakage_failure_count"] = len(source_leakage)
        summary["source_adapter_view_leakage_failures"] = source_leakage
        summary["typed_cards_adapter_view_leakage_failure_count"] = len(typed_leakage)
        summary["typed_cards_adapter_view_leakage_failures"] = typed_leakage
        summary["adapter_view_leakage_failure_count"] = len(typed_leakage)
        summary["adapter_view_leakage_failures"] = typed_leakage
        summary["typed_cards_setup_mutation_count"] = len(
            [
                mutation
                for mutation in typed_fixture.get("mutations") or []
                if mutation.get("mutation_type") == "seed_eval"
            ]
        )
        summary["typed_cards_fixture_hashes"] = {
            "fixture_public_hash": typed_views.fixture_public_hash,
            "fixture_gold_hash": typed_views.fixture_gold_hash,
            "fixture_full_hash": typed_views.fixture_full_hash,
        }
        summary["typed_cards_summary_search_backend"] = summary_search_backend
        summary["typed_cards_embedding_provider"] = (
            embedding_provider
            if summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None
        )
        summary["typed_cards_embedding_model_id"] = (
            embedding_model_id
            if summary_search_backend in TYPED_CARDS_VECTOR_BACKENDS
            else None
        )
        summary["typed_cards_live_model_backend"] = backend
        summary["typed_cards_live_model"] = model
        summary["typed_cards_live_call_interface"] = call_interface
        summary["typed_cards_live_artifact_path"] = str(artifact_path)
        summary["typed_cards_live_gating"] = False
        if typed_leakage:
            summary["result_status"] = "failed"
            summary["failure_types"] = sorted(
                {*summary["failure_types"], "typed_cards_adapter_view_leakage"}
            )
            summary["failed_gate_ids"] = sorted(
                {*summary["failed_gate_ids"], "no_label_leakage"}
            )
        results.append(summary)
    return results


def _typed_cards_unavailable_summary(
    *,
    preview: Mapping[str, Any],
    fixture_ordinal: int,
    error: Exception,
) -> dict[str, Any]:
    return {
        "fixture_ordinal": fixture_ordinal,
        "fixture_id": preview.get("fixture_id"),
        "adapter_fixture_id": preview.get("adapter_fixture_id"),
        "query_id_hash": preview.get("query_id_hash"),
        "result_status": "failed",
        "request_statuses": [],
        "failed_gate_ids": ["typed_cards_adapter_available"],
        "failure_types": ["typed_cards_adapter_unavailable"],
        "status_reason": str(error),
        "artifact_hashes": {},
        "fixture_hashes": {},
        "usage_summary": {},
    }


def _typed_cards_error_summary(
    *,
    preview: Mapping[str, Any],
    fixture_ordinal: int,
    error: Exception,
) -> dict[str, Any]:
    return {
        "fixture_ordinal": fixture_ordinal,
        "fixture_id": preview.get("fixture_id"),
        "adapter_fixture_id": preview.get("adapter_fixture_id"),
        "query_id_hash": preview.get("query_id_hash"),
        "result_status": "failed",
        "request_statuses": [],
        "failed_gate_ids": ["typed_cards_validation_run_completed"],
        "failure_types": ["typed_cards_validation_error"],
        "status_reason": str(error),
        "artifact_hashes": {},
        "fixture_hashes": {},
        "usage_summary": {},
    }


def _validation_seed(
    dry_run_report: Mapping[str, Any], *, explicit_seed: int | None
) -> int:
    if explicit_seed is not None:
        return explicit_seed
    report_seed = _optional_int(dry_run_report.get("seed"))
    if report_seed is not None:
        return report_seed
    for preview in dry_run_report.get("fixture_previews") or []:
        if not isinstance(preview, Mapping):
            continue
        adapter_view = preview.get("adapter_view") or {}
        if not isinstance(adapter_view, Mapping):
            continue
        preview_seed = _optional_int(adapter_view.get("seed"))
        if preview_seed is not None:
            return preview_seed
    return 12345


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _run_validation_summary(
    *,
    artifact: Mapping[str, Any],
    preview: Mapping[str, Any],
    fixture_ordinal: int,
) -> dict[str, Any]:
    requests = list(artifact.get("requests") or [])
    failed_gate_ids = sorted(
        {
            str(gate.get("gate_id"))
            for request in requests
            for gate in request.get("hard_gates") or []
            if gate.get("passed") is False
        }
    )
    failure_types = sorted(
        {
            str(failure.get("type"))
            for request in requests
            for failure in request.get("failures") or []
        }
    )
    result_statuses = [str(request.get("result_status")) for request in requests]
    return {
        "fixture_ordinal": fixture_ordinal,
        "fixture_id": preview.get("fixture_id"),
        "adapter_fixture_id": preview.get("adapter_fixture_id"),
        "query_id_hash": preview.get("query_id_hash"),
        "result_status": "passed"
        if result_statuses and all(status == "passed" for status in result_statuses)
        else "failed",
        "request_statuses": result_statuses,
        "failed_gate_ids": failed_gate_ids,
        "failure_types": failure_types,
        "artifact_hashes": dict(artifact.get("artifact_hashes") or {}),
        "fixture_hashes": dict(artifact.get("fixture") or {}),
        "hard_gate_summary": list(artifact.get("hard_gates") or []),
        "aggregate_metrics": dict(artifact.get("aggregate_metrics") or {}),
        "usage_summary": _usage_summary(artifact),
    }


def _negative_control_summary(
    *,
    artifact: Mapping[str, Any],
    preview: Mapping[str, Any],
    fixture_ordinal: int,
    control: Mapping[str, Any],
) -> dict[str, Any]:
    summary = _run_validation_summary(
        artifact=artifact,
        preview=preview,
        fixture_ordinal=fixture_ordinal,
    )
    expected_failure_types = set(control.get("expected_failure_types") or [])
    expected_gate_ids = set(control.get("expected_gate_ids") or [])
    observed_failure_types = set(summary["failure_types"])
    observed_gate_ids = set(summary["failed_gate_ids"])
    expected_observed = bool(
        expected_failure_types <= observed_failure_types
        and expected_gate_ids <= observed_gate_ids
        and summary["request_statuses"]
        and all(status == "failed" for status in summary["request_statuses"])
    )
    return {
        "control_id": control.get("control_id"),
        "adapter_id": control.get("adapter_id"),
        "fixture_ordinal": fixture_ordinal,
        "fixture_id": preview.get("fixture_id"),
        "adapter_fixture_id": preview.get("adapter_fixture_id"),
        "query_id_hash": preview.get("query_id_hash"),
        "expected_failure_types": sorted(expected_failure_types),
        "expected_gate_ids": sorted(expected_gate_ids),
        "observed_failure_types": summary["failure_types"],
        "observed_failed_gate_ids": summary["failed_gate_ids"],
        "negative_control_status": "passed" if expected_observed else "failed",
        "request_statuses": summary["request_statuses"],
        "artifact_hashes": summary["artifact_hashes"],
        "fixture_hashes": summary["fixture_hashes"],
        "hard_gate_summary": summary["hard_gate_summary"],
        "applicability": control.get("applicability"),
    }


def _usage_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    request_usage = [
        request.get("usage")
        for request in artifact.get("requests") or []
        if isinstance(request.get("usage"), Mapping)
    ]
    run_usage = (
        artifact.get("usage") if isinstance(artifact.get("usage"), Mapping) else {}
    )
    latency_sources = sorted(
        {
            str(((usage.get("latency_ms") or {}).get("source") or "unknown"))
            for usage in [*request_usage, run_usage]
            if isinstance(usage, Mapping) and usage.get("latency_ms") is not None
        }
    )
    count_totals: dict[str, int | float] = {}
    for usage in [*request_usage, run_usage]:
        counts = usage.get("counts") if isinstance(usage, Mapping) else None
        if not isinstance(counts, Mapping):
            continue
        for key, value in counts.items():
            if isinstance(value, (int, float)):
                count_totals[key] = count_totals.get(key, 0) + value
    return {
        "request_usage_count": len(request_usage),
        "run_usage_reported": bool(run_usage),
        "latency_sources": latency_sources,
        "count_totals": count_totals,
    }


def _applicable_negative_controls(
    fixture: Mapping[str, Any],
) -> list[dict[str, Any]]:
    experience_count = len(fixture.get("experiences") or [])
    controls = [
        {
            "control_id": "duplicate_support",
            "adapter_id": "memory_eval_broken_duplicate_support",
            "adapter_factory": DuplicateSupportAdapter,
            "expected_failure_types": ["duplicate_support_reference"],
            "expected_gate_ids": ["no_duplicate_support_reference"],
            "min_experiences": 1,
            "applicability": (
                "Uses the first applied public evidence ID twice, so it remains "
                "applicable to ordinary all-ingested MemBench dry-run fixtures."
            ),
        },
        {
            "control_id": "unscorable_evidence",
            "adapter_id": "memory_eval_broken_unscorable_evidence",
            "adapter_factory": UnscorableEvidenceAdapter,
            "expected_failure_types": ["unscorable_evidence"],
            "expected_gate_ids": ["required_support_mapping_present"],
            "min_experiences": 0,
            "applicability": (
                "Returns evidence without support_experience_ids, exercising "
                "the scorer support-mapping gate without fixture mutation."
            ),
        },
        {
            "control_id": "missing_usage",
            "adapter_id": "memory_eval_broken_missing_usage",
            "adapter_factory": MissingUsageAdapter,
            "expected_failure_types": ["missing_usage"],
            "expected_gate_ids": ["required_usage_present"],
            "min_experiences": 1,
            "applicability": (
                "Returns a normal-looking item but omits usage despite the "
                "manifest's latency-reporting capability."
            ),
        },
        {
            "control_id": "support_source_mismatch",
            "adapter_id": "memory_eval_broken_support_source_mismatch",
            "adapter_factory": SupportSourceMismatchAdapter,
            "expected_failure_types": ["support_source_mismatch"],
            "expected_gate_ids": ["support_source_consistency"],
            "min_experiences": 2,
            "applicability": (
                "Requires two applied public evidence IDs so support and "
                "source IDs can intentionally disagree."
            ),
        },
    ]
    return [
        control
        for control in controls
        if experience_count >= int(control.get("min_experiences") or 0)
    ]


def _negative_controls_not_run_notes() -> list[dict[str, str]]:
    return [
        {
            "control_id": "future_support",
            "adapter_id": "memory_eval_broken_future_support",
            "reason": (
                "MTEB qrels dry-run fixtures ingest the selected corpus before "
                "the request, so the hard-coded ex_000002 reference is not a "
                "future support reference without reshaping the fixture."
            ),
        },
        {
            "control_id": "cross_scope_exposure",
            "adapter_id": "memory_eval_broken_cross_scope_exposure",
            "reason": (
                "The dry-run converter intentionally emits one opaque scope; "
                "cross-scope gates need a fixture with a second scorer-visible "
                "scope."
            ),
        },
        {
            "control_id": "stale_as_fresh",
            "adapter_id": "memory_eval_broken_stale_as_fresh",
            "reason": (
                "MTEB qrels dry-run previews have no mutation sequence or "
                "stale evidence gold, so stale controls belong to future "
                "update/supersede MemBench fixtures."
            ),
        },
    ]


def _validation_result_summary(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    status_counts = _counts(str(result.get("result_status")) for result in results)
    hash_mismatch_count = sum(
        1 for result in results if not all((result.get("hash_match") or {}).values())
    )
    leakage_failure_count = sum(
        int(result.get("adapter_view_leakage_failure_count") or 0) for result in results
    )
    return {
        "example_count": len(results),
        "status_counts": status_counts,
        "passed": bool(results)
        and status_counts.get("passed", 0) == len(results)
        and hash_mismatch_count == 0
        and leakage_failure_count == 0,
        "hash_mismatch_count": hash_mismatch_count,
        "adapter_view_leakage_failure_count": leakage_failure_count,
    }


def _negative_control_result_summary(
    results: list[Mapping[str, Any]],
) -> dict[str, Any]:
    status_counts = _counts(
        str(result.get("negative_control_status")) for result in results
    )
    return {
        "run_count": len(results),
        "status_counts": status_counts,
        "passed": bool(results) and status_counts.get("passed", 0) == len(results),
    }


def _validation_status(report: Mapping[str, Any]) -> str:
    reference = (report.get("reference_adapter") or {}).get("result_summary") or {}
    typed_cards = (report.get("typed_cards_adapter") or {}).get("result_summary") or {}
    controls = (report.get("negative_controls") or {}).get("result_summary") or {}
    if not report.get("selected_fixture_count"):
        return "failed"
    if not reference.get("passed"):
        return "failed"
    typed_cards_adapter = report.get("typed_cards_adapter") or {}
    if (
        typed_cards_adapter.get("run")
        and typed_cards_adapter.get("gating", True)
        and not typed_cards.get("passed")
    ):
        return "failed"
    if (report.get("negative_controls") or {}).get("run") and not controls.get(
        "passed"
    ):
        return "failed"
    return "passed"


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _validated_redistribution_status(value: Any) -> str:
    status = str(value or "private_only")
    if status not in REDISTRIBUTION_STATUSES:
        raise MembenchConversionError(
            "redistribution_status must be one of "
            + ", ".join(REDISTRIBUTION_STATUSES)
        )
    return status


def _redistribution_review_manifest(
    *,
    existing: Any,
    approved: bool | None,
    reviewer: str | None,
    reviewed_at: str | None,
    decision_basis: str | None,
    scope: str | None,
) -> dict[str, Any]:
    review = dict(existing) if isinstance(existing, Mapping) else {}
    if approved is not None:
        review["approved"] = approved
    if reviewer is not None:
        review["reviewer"] = reviewer
    if reviewed_at is not None:
        review["reviewed_at"] = reviewed_at
    if decision_basis is not None:
        review["decision_basis"] = decision_basis
    if scope is not None:
        review["scope"] = scope
    return review


def _is_pinned_revision(value: Any) -> bool:
    revision = str(value or "").strip()
    return bool(PINNED_REVISION_RE.fullmatch(revision))


def _missing_phase_c_commit_fields(manifest: Mapping[str, Any]) -> list[str]:
    missing = []
    required_non_placeholder_text_fields = [
        "source_dataset",
        "source_host",
        "declared_license",
        "license_source",
    ]
    for field in required_non_placeholder_text_fields:
        if _manifest_text_missing(manifest.get(field)) or _is_placeholder_text(
            manifest.get(field)
        ):
            missing.append(field)
    if not _is_absolute_non_placeholder_url(manifest.get("source_url")):
        missing.append("source_url:absolute")
    if not _is_pinned_revision(manifest.get("source_revision")):
        missing.append("source_revision:immutable")
    if manifest.get("source_revision_status") != "pinned":
        missing.append("source_revision_status:pinned")
    if not manifest.get("local_cache_only"):
        missing.append("local_cache_only:true")
    if not _is_absolute_non_placeholder_url(manifest.get("license_source_url")):
        _append_missing_once(missing, "license_source_url:absolute")
    if manifest.get("generated_fixture_commit_policy") != "no_vendor_by_default":
        _append_missing_once(
            missing,
            "generated_fixture_commit_policy:no_vendor_by_default",
        )
    if _manifest_text_missing(manifest.get("declared_license")) or str(
        manifest.get("declared_license") or ""
    ).lower() == "unreviewed":
        _append_missing_once(missing, "declared_license")
    if _manifest_text_missing(manifest.get("license_source")) or str(
        manifest.get("license_source") or ""
    ).lower() == "source audit required":
        _append_missing_once(missing, "license_source")
    citation_targets = manifest.get("citation_targets")
    if manifest.get("citation_required", True) and not citation_targets:
        missing.append("citation_targets")
    raw_hashes = manifest.get("raw_file_hashes") or []
    if not raw_hashes:
        missing.append("raw_file_hashes")
    else:
        for index, item in enumerate(raw_hashes):
            if not isinstance(item, Mapping) or _manifest_text_missing(
                item.get("path")
            ) or not _is_full_sha256_digest(item.get("sha256")):
                missing.append(f"raw_file_hashes[{index}]")
                break
    notice_requirements = manifest.get("notice_requirements") or {}
    notice_file = manifest.get("third_party_notice_file")
    if _manifest_text_missing(notice_file) and isinstance(
        notice_requirements, Mapping
    ):
        notice_file = notice_requirements.get("notice_file")
    if _manifest_text_missing(notice_file):
        missing.append("third_party_notice_file")
    if not isinstance(notice_requirements, Mapping) or not notice_requirements.get(
        "required_if_generated_fixtures_committed"
    ):
        missing.append("notice_requirements.required_if_generated_fixtures_committed")
    for flag in (
        "include_declared_license",
        "include_citation_targets",
        "include_source_provenance",
    ):
        if not isinstance(notice_requirements, Mapping) or not notice_requirements.get(
            flag
        ):
            missing.append(f"notice_requirements.{flag}")
    missing.extend(_missing_redistribution_review_fields(manifest))
    return missing


def _missing_redistribution_review_fields(
    manifest: Mapping[str, Any],
) -> list[str]:
    review = manifest.get("redistribution_review")
    if not isinstance(review, Mapping):
        return [
            "redistribution_review.approved:true",
            "redistribution_review.reviewer",
            "redistribution_review.reviewed_at",
            "redistribution_review.decision_basis",
            "redistribution_review.scope:generated_fixtures_only",
        ]

    missing = []
    if review.get("approved") is not True:
        missing.append("redistribution_review.approved:true")
    if _manifest_text_missing(review.get("reviewer")) or _is_placeholder_text(
        review.get("reviewer")
    ):
        missing.append("redistribution_review.reviewer")
    if not _is_reviewed_at_value(review.get("reviewed_at")):
        missing.append("redistribution_review.reviewed_at")
    if _manifest_text_missing(review.get("decision_basis")) or _is_placeholder_text(
        review.get("decision_basis")
    ):
        missing.append("redistribution_review.decision_basis")
    if review.get("scope") != REDISTRIBUTION_REVIEW_SCOPE:
        missing.append("redistribution_review.scope:generated_fixtures_only")
    return missing


def _manifest_text_missing(value: Any) -> bool:
    return not str(value or "").strip()


def _is_placeholder_text(value: Any) -> bool:
    return str(value or "").strip().lower() in PLACEHOLDER_TEXT_VALUES


def _is_absolute_non_placeholder_url(value: Any) -> bool:
    text = str(value or "").strip()
    if _is_placeholder_text(text):
        return False
    return bool(re.fullmatch(r"https?://[^/\s]+(?:/[^ \t\r\n]*)?", text))


def _is_full_sha256_digest(value: Any) -> bool:
    return bool(SHA256_DIGEST_RE.fullmatch(str(value or "").strip()))


def _is_reviewed_at_value(value: Any) -> bool:
    text = str(value or "").strip()
    if _is_placeholder_text(text):
        return False
    if not REVIEWED_AT_RE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _append_missing_once(missing: list[str], field: str) -> None:
    if field not in missing:
        missing.append(field)


def _source_audit_finding(
    *, severity: str, field: str, message: str
) -> dict[str, Any]:
    return {"severity": severity, "field": field, "message": message}


def _load_default_manifest(root: Path) -> dict[str, Any]:
    for name in (
        "source_manifest.json",
        "membench_source_manifest.json",
        "manifest.json",
    ):
        candidate = root / name
        if candidate.exists():
            return _load_json_object(candidate)
    return {}


def _load_json_object(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise MembenchConversionError(f"Expected JSON object in {path}")
    return value


def _find_source_files(
    root: Path, manifest: Mapping[str, Any] | None = None
) -> PreparedMtebSource:
    manifest = manifest or {}
    source_files = manifest.get("source_files") or {}
    corpus_path = _manifest_path(root, source_files, "corpus") or _first_existing(
        root,
        [
            "corpus.jsonl",
            "corpus.json",
            "corpus/corpus.jsonl",
            "corpus/corpus.json",
            "data/corpus.jsonl",
            "data/corpus.json",
        ],
        recursive_names=("corpus.jsonl", "corpus.json"),
    )
    queries_path = _manifest_path(root, source_files, "queries") or _first_existing(
        root,
        [
            "queries.jsonl",
            "queries.json",
            "queries/queries.jsonl",
            "queries/queries.json",
            "data/queries.jsonl",
            "data/queries.json",
        ],
        recursive_names=("queries.jsonl", "queries.json"),
    )
    qrels_path = _manifest_path(root, source_files, "qrels") or _first_existing(
        root,
        [
            "qrels.jsonl",
            "qrels.json",
            "qrels.tsv",
            "qrels/test.tsv",
            "qrels/dev.tsv",
            "qrels/train.tsv",
            "data/qrels.jsonl",
            "data/qrels.tsv",
        ],
        recursive_names=("qrels.jsonl", "qrels.json", "qrels.tsv"),
    )
    top_ranked_path = _manifest_path(
        root, source_files, "top_ranked"
    ) or _first_existing(
        root,
        [
            "top_ranked.jsonl",
            "top_ranked.json",
            "top_ranked.tsv",
            "data/top_ranked.jsonl",
            "data/top_ranked.tsv",
        ],
        recursive_names=("top_ranked.jsonl", "top_ranked.json", "top_ranked.tsv"),
        required=False,
    )
    missing = [
        name
        for name, path in (
            ("corpus", corpus_path),
            ("queries", queries_path),
            ("qrels", qrels_path),
        )
        if path is None
    ]
    if missing:
        raise MembenchConversionError(
            f"Missing required MTEB source files: {', '.join(missing)}"
        )
    assert corpus_path is not None
    assert queries_path is not None
    assert qrels_path is not None
    return PreparedMtebSource(
        source_dir=root,
        corpus_path=corpus_path,
        queries_path=queries_path,
        qrels_path=qrels_path,
        top_ranked_path=top_ranked_path,
        manifest_path=None,
    )


def _manifest_path(
    root: Path, source_files: Mapping[str, Any], key: str
) -> Path | None:
    value = source_files.get(key)
    if isinstance(value, Mapping):
        value = value.get("path") or value.get("relative_path")
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = root / path
    return path if path.exists() else None


def _first_existing(
    root: Path,
    relative_paths: Iterable[str],
    *,
    recursive_names: Iterable[str],
    required: bool = True,
) -> Path | None:
    for relative in relative_paths:
        candidate = root / relative
        if candidate.exists():
            return candidate
    matches = []
    for name in recursive_names:
        matches.extend(root.rglob(name))
    matches = sorted(path for path in matches if path.is_file())
    if matches:
        return matches[0]
    if required:
        return None
    return None


def _hf_mteb_config_names(
    subset: str, *, include_top_ranked: bool
) -> dict[str, str]:
    names = {
        "corpus": f"{subset}-corpus",
        "queries": f"{subset}-queries",
        "qrels": f"{subset}-qrels",
    }
    if include_top_ranked:
        names["top_ranked"] = f"{subset}-top_ranked"
    return names


def _default_hf_dataset_loader(
    dataset: str, config_name: str, *, revision: str
) -> Any:
    try:
        from datasets import DownloadConfig, load_dataset
    except ModuleNotFoundError as exc:
        raise MembenchConversionError(
            "Development dependency 'datasets' is required to prepare Hugging "
            "Face MemBench sources. Install the dev dependencies or pass an "
            "injected loader in tests."
        ) from exc
    except ImportError as exc:
        raise MembenchConversionError(
            "Development dependency 'datasets' must support "
            "DownloadConfig(local_files_only=True) for local/cache-only MemBench "
            "preparation. Upgrade datasets or pass an injected local-only loader."
        ) from exc

    return load_dataset(
        dataset,
        config_name,
        revision=revision,
        download_config=DownloadConfig(local_files_only=True),
    )


def _load_hf_config_records(
    *,
    loader: HfDatasetLoader,
    dataset: str,
    config_name: str,
    revision: str,
    split: str | None,
) -> list[dict[str, Any]]:
    try:
        loaded = loader(dataset, config_name, revision=revision)
    except MembenchConversionError:
        raise
    except Exception as exc:
        raise MembenchConversionError(
            f"Failed to load Hugging Face config {config_name!r} from "
            f"{dataset!r}: {exc}"
        ) from exc

    selected = _select_hf_dataset_split(loaded, split=split, config_name=config_name)
    records = _materialize_hf_records(selected, config_name=config_name)
    if not records:
        raise MembenchConversionError(
            f"Hugging Face config {config_name!r} produced no records"
        )
    return records


def _select_hf_dataset_split(
    value: Any, *, split: str | None, config_name: str
) -> Any:
    if split is not None:
        if isinstance(value, Mapping) and split in value:
            return value[split]
        try:
            return value[split]
        except (KeyError, TypeError):
            raise MembenchConversionError(
                f"Hugging Face config {config_name!r} does not contain split "
                f"{split!r}"
            ) from None

    if hasattr(value, "to_list") or _is_record_sequence(value):
        return value
    if isinstance(value, Mapping):
        for candidate in ("test", "dev", "validation", "train"):
            if candidate in value:
                return value[candidate]
        if "rows" in value or "data" in value or _looks_like_nested_qrels(value):
            return value
        if len(value) == 1:
            return next(iter(value.values()))
        raise MembenchConversionError(
            f"Hugging Face config {config_name!r} has multiple splits; pass --split"
        )
    return value


def _materialize_hf_records(value: Any, *, config_name: str) -> list[dict[str, Any]]:
    if hasattr(value, "to_list"):
        rows = value.to_list()
    elif isinstance(value, Mapping):
        rows_value = value.get("rows")
        if rows_value is None:
            rows_value = value.get("data")
        if isinstance(rows_value, list):
            rows = rows_value
        elif _looks_like_nested_qrels(value):
            rows = [value]
        else:
            rows = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        rows = list(value)
    else:
        raise MembenchConversionError(
            f"Hugging Face config {config_name!r} is not iterable"
        )

    records = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise MembenchConversionError(
                f"Hugging Face config {config_name!r} row {index} is not a record"
            )
        records.append(dict(row))
    return records


def _is_record_sequence(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, Mapping) for item in value)
    )


def _write_jsonl_records(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_json_ready(record), sort_keys=True) + "\n")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(child) for child in value]
    if isinstance(value, list):
        return [_json_ready(child) for child in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "item"):
        try:
            return _json_ready(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _hf_dataset_url(dataset: str) -> str:
    return (
        MEMBENCH_HF_DATASET_URL
        if dataset == MEMBENCH_HF_DATASET
        else f"https://huggingface.co/datasets/{dataset}"
    )


def _reject_memory_eval_fixture_output(path: Path) -> None:
    target = path.resolve()
    fixtures = MEMORY_EVAL_FIXTURES_DIR.resolve()
    if target == fixtures or fixtures in target.parents:
        raise MembenchConversionError(
            "Hugging Face MemBench preparation writes raw local source data; "
            "choose an output directory outside fixtures/memory_eval"
        )


def _refresh_source_manifest_hash(manifest: dict[str, Any]) -> None:
    manifest["source_manifest_hash"] = stable_hash(
        {key: value for key, value in manifest.items() if key != "source_manifest_hash"}
    )


def _source_file_manifest(source: PreparedMtebSource) -> dict[str, Any]:
    paths = {
        "corpus": source.corpus_path,
        "queries": source.queries_path,
        "qrels": source.qrels_path,
        "top_ranked": source.top_ranked_path,
    }
    result = {}
    for key, path in paths.items():
        if path is None:
            continue
        result[key] = {"path": _relative_or_absolute(source.source_dir, path)}
    return result


def _raw_file_hashes(source: PreparedMtebSource) -> list[dict[str, Any]]:
    paths = [source.corpus_path, source.queries_path, source.qrels_path]
    if source.top_ranked_path is not None:
        paths.append(source.top_ranked_path)
    hashes = []
    for path in paths:
        if not path.exists():
            continue
        hashes.append(
            {
                "path": _relative_or_absolute(source.source_dir, path),
                "sha256": "sha256:" + _file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return hashes


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_corpus(path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    records = _load_records(path)
    duplicate_doc_ids = {
        item
        for item, count in Counter(
            _record_id(record, CORPUS_ID_KEYS) for record in records
        ).items()
        if item and count > 1
    }
    normalized = []
    for index, record in enumerate(records, start=1):
        doc_id = _record_id(record, CORPUS_ID_KEYS)
        if not doc_id:
            continue
        normalized.append(
            {
                "source_doc_id": doc_id,
                "title": str(record.get("title") or ""),
                "text": _record_text(record, ("text", "contents", "document", "body")),
                "raw_keys": sorted(str(key) for key in record),
                "source_order": index,
            }
        )
    return normalized, duplicate_doc_ids


def _load_queries(path: Path) -> dict[str, dict[str, Any]]:
    records = _load_records(path)
    queries = {}
    for index, record in enumerate(records, start=1):
        query_id = _record_id(record, QUERY_ID_KEYS)
        if not query_id:
            continue
        queries[query_id] = {
            "query_id": query_id,
            "text": _record_text(record, ("text", "query", "question")),
            "raw_keys": sorted(str(key) for key in record),
            "source_order": index,
        }
    return queries


def _load_qrels(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return _load_tsv_qrels(path)
    records = _load_records(path, allow_nested_qrels=True)
    qrels = []
    for record in records:
        if _looks_like_nested_qrels(record):
            for query_id, docs in record.items():
                if isinstance(docs, Mapping):
                    for doc_id, score in docs.items():
                        _append_qrel(qrels, query_id, doc_id, score)
            continue
        query_id = _record_id(record, QREL_QUERY_ID_KEYS)
        doc_id = _record_id(record, QREL_DOC_ID_KEYS)
        score = _first_present(record, QREL_SCORE_KEYS)
        _append_qrel(qrels, query_id, doc_id, score)
    return qrels


def _validate_corpus_sample_policy(policy: str) -> str:
    if policy not in CORPUS_SAMPLE_POLICIES:
        raise MembenchConversionError(
            "corpus_sample_policy must be one of "
            + ", ".join(CORPUS_SAMPLE_POLICIES)
        )
    return policy


def _corpus_by_doc_id(
    corpus_records: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in corpus_records:
        doc_id = str(record.get("source_doc_id") or "")
        if doc_id and doc_id not in result:
            result[doc_id] = record
    return result


def _selected_corpus_doc_ids(
    *,
    full_doc_ids: list[str],
    query_id: str,
    query_qrels: list[dict[str, Any]],
    policy: str,
    max_corpus_docs: int | None,
    seed: int,
) -> list[str]:
    qrel_doc_ids = [
        str(row["source_doc_id"])
        for row in sorted(
            query_qrels, key=lambda item: (str(item["source_doc_id"]), item["score"])
        )
    ]
    if policy == "full":
        return list(full_doc_ids)

    assert max_corpus_docs is not None
    selected = []
    for doc_id in qrel_doc_ids:
        if doc_id not in selected:
            selected.append(doc_id)
    remaining_slots = max(0, max_corpus_docs - len(selected))
    candidates = [doc_id for doc_id in full_doc_ids if doc_id not in selected]
    if policy == "qrel_plus_prefix":
        selected.extend(candidates[:remaining_slots])
    elif policy == "qrel_plus_random":
        selected.extend(
            _deterministic_sample(
                candidates,
                limit=remaining_slots,
                seed=seed,
                query_id=query_id,
            )
        )
    return selected


def _deterministic_sample(
    values: list[str], *, limit: int, seed: int, query_id: str
) -> list[str]:
    if limit <= 0:
        return []
    if limit >= len(values):
        return list(values)
    rng_seed = stable_hash({"seed": seed, "query_id": query_id})
    rng = random.Random(rng_seed)
    indexes = sorted(rng.sample(range(len(values)), limit))
    return [values[index] for index in indexes]


def _corpus_sampling_report(
    *,
    policy: str,
    max_corpus_docs: int | None,
    effective_corpus_docs: int,
    total_corpus_docs: int,
    query_qrels: list[dict[str, Any]],
    selected_doc_ids: list[str],
) -> dict[str, Any]:
    qrel_doc_ids = sorted({str(row["source_doc_id"]) for row in query_qrels})
    selected = set(selected_doc_ids)
    return {
        "policy": policy,
        "max_corpus_docs": max_corpus_docs,
        "effective_corpus_docs": effective_corpus_docs,
        "total_corpus_docs": total_corpus_docs,
        "qrel_doc_count": len(qrel_doc_ids),
        "qrel_docs_included": all(doc_id in selected for doc_id in qrel_doc_ids),
    }


def _load_tsv_qrels(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            has_header = csv.Sniffer().has_header(sample) if sample.strip() else False
        except csv.Error:
            has_header = False
        if has_header:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)
        else:
            reader = csv.reader(handle, delimiter="\t")
            rows = [
                {
                    "query-id": row[0],
                    "corpus-id": row[1],
                    "score": row[2] if len(row) > 2 else 1,
                }
                for row in reader
                if len(row) >= 2
            ]
    qrels = []
    for row in rows:
        query_id = _record_id(row, QREL_QUERY_ID_KEYS)
        doc_id = _record_id(row, QREL_DOC_ID_KEYS)
        score = _first_present(row, QREL_SCORE_KEYS)
        _append_qrel(qrels, query_id, doc_id, score)
    return qrels


def _load_records(
    path: Path, *, allow_nested_qrels: bool = False
) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    with path.open("r", encoding="utf-8") as handle:
        if suffix == ".jsonl":
            return [json.loads(line) for line in handle if line.strip()]
        value = json.load(handle)
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        if "rows" in value and isinstance(value["rows"], list):
            return [dict(item) for item in value["rows"] if isinstance(item, Mapping)]
        if "data" in value and isinstance(value["data"], list):
            return [dict(item) for item in value["data"] if isinstance(item, Mapping)]
        if allow_nested_qrels and _looks_like_nested_qrels(value):
            return [dict(value)]
        records = []
        for key, item in value.items():
            if isinstance(item, Mapping):
                row = dict(item)
                row.setdefault("_id", key)
                records.append(row)
        return records
    raise MembenchConversionError(f"Unsupported JSON structure in {path}")


def _append_qrel(
    qrels: list[dict[str, Any]], query_id: Any, doc_id: Any, score: Any
) -> None:
    if query_id is None or doc_id is None:
        return
    numeric_score = _numeric_score(score)
    if numeric_score <= 0:
        return
    qrels.append(
        {
            "query_id": str(query_id),
            "source_doc_id": str(doc_id),
            "score": numeric_score,
        }
    )


def _numeric_score(value: Any) -> float:
    if value is None or value == "":
        return 1.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _build_corpus_manifest(
    corpus_records: list[dict[str, Any]],
    *,
    manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    corpus_manifest = []
    doc_to_experience = {}
    seen: set[str] = set()
    for index, record in enumerate(corpus_records, start=1):
        doc_id = str(record["source_doc_id"])
        experience_id = f"exp_src_{index:06d}"
        if doc_id not in seen:
            doc_to_experience[doc_id] = experience_id
        seen.add(doc_id)
        locator = {
            "source_dataset": manifest.get("source_dataset") or MEMBENCH_HF_DATASET,
            "source_revision": manifest.get("source_revision") or "unresolved",
            "source_subset": manifest.get("source_subset"),
            "source_doc_id": doc_id,
        }
        corpus_manifest.append(
            {
                "source_doc_id_hash": stable_hash(doc_id),
                "experience_id": experience_id,
                "source_locator_hash": stable_hash(locator),
                "source_text_hash": stable_hash(
                    {
                        "title": record.get("title") or "",
                        "text": record.get("text") or "",
                    }
                ),
            }
        )
    return corpus_manifest, doc_to_experience


def _fixture_base(
    *,
    corpus_records: list[dict[str, Any]],
    corpus_manifest: list[dict[str, Any]],
    source: PreparedMtebSource,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    experiences = []
    for index, record in enumerate(corpus_records, start=1):
        manifest_row = corpus_manifest[index - 1]
        text = _public_corpus_text(record)
        experiences.append(
            {
                "experience_id": manifest_row["experience_id"],
                "scope_id": DEFAULT_SCOPE_ID,
                "session_id": f"session_{index:06d}",
                "turn_id": f"turn_{index:06d}",
                "event_time": "2026-05-21T00:00:00Z",
                "ingest_order": index,
                "actor_id": "source_observer",
                "payload": {"mime_type": "text/plain", "text": text},
                "visibility": {
                    "allowed_scope_ids": [DEFAULT_SCOPE_ID],
                    "retrievable": True,
                },
                "metadata": {"source_kind": "synthetic_memory_observation"},
            }
        )
    source_benchmark = {
        "benchmark_id": "membench",
        "source_mode": "mteb_huggingface_qrels",
        "source_dataset": manifest.get("source_dataset") or MEMBENCH_HF_DATASET,
        "source_revision": manifest.get("source_revision") or "unresolved",
        "source_subset": manifest.get("source_subset"),
        "source_file_sha256": _source_file_hash_lookup(manifest, source.qrels_path),
        "source_path": _relative_or_absolute(source.source_dir, source.qrels_path),
        "converter_id": CONVERTER_ID,
        "converter_version": CONVERTER_VERSION,
        "source_manifest_hash": manifest.get("source_manifest_hash"),
    }
    return {
        "schema_version": "memory_eval_fixture.v1",
        "fixture_id": "membench_mteb_qrels_dry_run",
        "fixture_version": "0.1.0",
        "fixture_family": "membench_mteb_qrels_dry_run",
        "label_leakage_blocked_tokens": [],
        "phase": "P1",
        "evaluation_time": DEFAULT_EVALUATION_TIME,
        "source_benchmark": source_benchmark,
        "experiences": experiences,
        "mutations": [],
        "requests": [],
        "operation_sequence": [],
    }


def _request_for_query(
    *,
    request_index: int,
    query_id: str,
    query: Mapping[str, Any],
    query_qrels: list[dict[str, Any]],
    corpus_manifest: list[dict[str, Any]],
    doc_to_experience: Mapping[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    relevant_ids = sorted(
        {doc_to_experience[str(row["source_doc_id"])] for row in query_qrels}
    )
    source_locator_by_exp = {
        row["experience_id"]: row["source_locator_hash"] for row in corpus_manifest
    }
    source_qrels = [
        {
            "source_doc_id_hash": stable_hash(row["source_doc_id"]),
            "experience_id": doc_to_experience[str(row["source_doc_id"])],
            "source_locator_hash": source_locator_by_exp[
                doc_to_experience[str(row["source_doc_id"])]
            ],
            "score": row["score"],
        }
        for row in sorted(
            query_qrels, key=lambda item: (str(item["source_doc_id"]), item["score"])
        )
    ]
    request = {
        "request_id": f"req_membench_mteb_qrels_{request_index:06d}",
        "mode": "membench_mteb_qrels_support_retrieval",
        "scope_id": DEFAULT_SCOPE_ID,
        "query_time": DEFAULT_QUERY_TIME,
        "query": {"text": str(query.get("text") or ""), "intent": "memory_lookup"},
        "k": 5,
        "filters": {"valid_at": DEFAULT_QUERY_TIME, "allowed_states": ["active"]},
        "budget": {
            "max_evidence_items": 5,
            "max_latency_ms": 500,
            "max_cost_units": None,
        },
        "requires_capabilities": ["retrieve"],
        "on_unsupported": "hard_failure",
        "gold": {
            "relevant_evidence_ids": relevant_ids,
            "must_not_return_evidence_ids": [],
            "stale_evidence_ids": [],
            "expected_abstention": False,
            "acceptable_support_sets": [[item] for item in relevant_ids],
            "support_coverage_policy": "any_relevant",
            "source_mode": "mteb_huggingface_qrels",
            "source_query_id_hash": stable_hash(query_id),
        },
    }
    return request, source_qrels


def _query_rejection(
    *,
    query_id: str,
    query: Mapping[str, Any] | None,
    query_qrels: list[dict[str, Any]],
    doc_to_experience: Mapping[str, str],
    duplicate_doc_ids: set[str],
) -> dict[str, Any] | None:
    if query is None:
        return {
            "query_id_hash": stable_hash(query_id),
            "reason": "missing_query",
            "doc_id_hashes": [],
        }
    if not str(query.get("text") or "").strip():
        return {
            "query_id_hash": stable_hash(query_id),
            "reason": "missing_query_text",
            "doc_id_hashes": [],
        }
    if not query_qrels:
        return {
            "query_id_hash": stable_hash(query_id),
            "reason": "missing_positive_qrels",
            "doc_id_hashes": [],
        }
    doc_ids = [str(row["source_doc_id"]) for row in query_qrels]
    ambiguous = sorted(set(doc_ids) & duplicate_doc_ids)
    if ambiguous:
        return {
            "query_id_hash": stable_hash(query_id),
            "reason": "ambiguous_qrel_doc",
            "doc_id_hashes": [stable_hash(item) for item in ambiguous],
        }
    missing = sorted({doc_id for doc_id in doc_ids if doc_id not in doc_to_experience})
    if missing:
        return {
            "query_id_hash": stable_hash(query_id),
            "reason": "missing_qrel_doc",
            "doc_id_hashes": [stable_hash(item) for item in missing],
        }
    return None


def _hash_sensitivity(
    fixture: Mapping[str, Any], *, fixture_ordinal: int, seed: int
) -> dict[str, Any]:
    baseline = split_fixture(fixture, fixture_ordinal=fixture_ordinal, seed=seed)
    changed = deepcopy(fixture)
    changed["requests"][0]["gold"]["source_qrels"][0]["score"] = (
        changed["requests"][0]["gold"]["source_qrels"][0].get("score", 1.0) + 1.0
    )
    changed["source_benchmark"]["source_revision"] = "hash-sensitivity-probe"
    changed_views = split_fixture(changed, fixture_ordinal=fixture_ordinal, seed=seed)
    return {
        "changed_fields": [
            "requests[].gold.source_qrels[].score",
            "source_benchmark.source_revision",
        ],
        "public_hash_unchanged": baseline.fixture_public_hash
        == changed_views.fixture_public_hash,
        "gold_hash_changed": baseline.fixture_gold_hash
        != changed_views.fixture_gold_hash,
        "full_hash_changed": baseline.fixture_full_hash
        != changed_views.fixture_full_hash,
    }


def _adapter_view_check_summary(
    leakage_results: list[dict[str, Any]],
) -> dict[str, Any]:
    failure_count = sum(int(item["failure_count"]) for item in leakage_results)
    return {
        "passed": failure_count == 0,
        "fixture_count": len(leakage_results),
        "failure_count": failure_count,
    }


def _group_qrels(qrels: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in qrels:
        grouped[str(row["query_id"])].append(row)
    return dict(grouped)


def _label_like_keys(*record_groups: Iterable[Mapping[str, Any]]) -> list[str]:
    keys = set()
    private = MEMBENCH_PRIVATE_STRUCTURAL_KEYS | {
        "answer",
        "ground_truth",
        "choices",
        "target_step_id",
    }
    for group in record_groups:
        for record in group:
            for key in record.get("raw_keys", record.keys()):
                normalized = _normalize_key(str(key))
                if normalized in private:
                    keys.add(str(key))
    return sorted(keys)


def _record_id(record: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    value = _first_present(record, keys)
    return str(value) if value is not None and str(value) != "" else None


def _record_text(record: Mapping[str, Any], keys: Iterable[str]) -> str:
    value = _first_present(record, keys)
    return str(value or "")


def _first_present(record: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _looks_like_nested_qrels(value: Mapping[str, Any]) -> bool:
    return bool(value) and all(isinstance(child, Mapping) for child in value.values())


def _public_corpus_text(record: Mapping[str, Any]) -> str:
    title = str(record.get("title") or "").strip()
    text = str(record.get("text") or "").strip()
    if title and text:
        return f"{title}\n\n{text}"
    return text or title


def _source_file_hash_lookup(manifest: Mapping[str, Any], path: Path) -> str | None:
    path_name = str(path)
    path_base = path.name
    for item in manifest.get("raw_file_hashes") or []:
        candidate = str(item.get("path") or "")
        if (
            candidate == path_name
            or candidate == path_base
            or candidate.endswith("/" + path_base)
        ):
            return item.get("sha256")
    return None


def _source_subset_value(value: str | Iterable[str] | None) -> str | list[str] | None:
    if value is None or isinstance(value, str):
        return value
    values = [str(item) for item in value]
    return values[0] if len(values) == 1 else values


def _relative_or_absolute(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _walk_with_keys(value: Any, path: str = "$"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from _walk_with_keys(child, child_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            if not isinstance(child, (Mapping, list)):
                yield f"{path}[{index}]", f"[{index}]", child
                continue
            yield from _walk_with_keys(child, f"{path}[{index}]")


def _normalize_key(value: str) -> str:
    return value.lower().replace("-", "_")


def _leak_failure(*, path: str, token: str, message: str) -> dict[str, Any]:
    return {
        "stage": "artifact",
        "severity": "error",
        "type": "label_leakage",
        "message": message,
        "gate_id": "no_label_leakage",
        "expected": "no MemBench scorer-only source data in adapter view",
        "actual": {"path": path, "token": token},
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
