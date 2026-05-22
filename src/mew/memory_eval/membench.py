"""MemBench external-source audit and MTEB qrels dry-run conversion.

This module intentionally supports local/cache-only dry runs. It does not
download MemBench data, vendor raw sources, or write committed fixture packs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .fixtures import find_label_leakage, split_fixture
from .hashing import stable_hash


SOURCE_MANIFEST_SCHEMA_VERSION = "mew_membench_source_manifest.v1"
DRY_RUN_SCHEMA_VERSION = "mew_membench_mteb_qrels_dry_run.v1"
CONVERTER_ID = "mew_membench_mteb_qrels_converter"
CONVERTER_VERSION = "0.1.0"
MEMBENCH_HF_DATASET = "mteb/MemBench"
DEFAULT_EVALUATION_TIME = "2026-05-22T00:00:00Z"
DEFAULT_SCOPE_ID = "tenant_mb/user_000001"
DEFAULT_QUERY_TIME = "2026-05-22T00:00:00Z"

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
    source_revision: str | None = None,
    source_subset: str | Iterable[str] | None = None,
    declared_license: str | None = None,
    license_source: str | None = None,
    citation_required: bool = True,
    citation_targets: Iterable[str] | None = None,
    redistribution_status: str = "private_only",
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
    targets = (
        list(citation_targets)
        if citation_targets is not None
        else list(existing.get("citation_targets") or [])
    )
    if not targets:
        targets = ["mteb/MemBench dataset card", "MTEB"]

    warnings = []
    if not revision or str(revision).lower() in {
        "latest",
        "main",
        "master",
        "unresolved",
    }:
        warnings.append("source_revision is not pinned to an immutable revision")
    if not license_value:
        warnings.append(
            "declared_license is missing; redistribution remains unresolved"
        )
    if not raw_hashes:
        warnings.append("no local raw source files were found for hashing")
    if redistribution_status not in {"private_only", "commit_allowed", "blocked"}:
        warnings.append(
            f"redistribution_status {redistribution_status!r} is not a recognized status"
        )

    manifest = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "source_mode": "external_huggingface",
        "source_dataset": source_dataset,
        "source_revision": revision or "unresolved",
        "source_revision_status": "pinned"
        if revision
        and str(revision).lower() not in {"latest", "main", "master", "unresolved"}
        else "unresolved",
        "source_subset": subset,
        "declared_license": license_value or "unreviewed",
        "license_source": license_origin or "source audit required",
        "license_certainty": "declared_unverified" if license_value else "unknown",
        "citation_required": bool(citation_required),
        "citation_targets": targets,
        "local_cache_only": True,
        "generated_fixture_commit_policy": "no_vendor_by_default",
        "redistribution_status": redistribution_status,
        "redistribution_certainty": "reviewer_required",
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


def convert_mteb_qrels_dry_run(
    source_dir: str | Path,
    *,
    source_manifest: Mapping[str, Any] | None = None,
    manifest_path: str | Path | None = None,
    source_revision: str | None = None,
    source_subset: str | Iterable[str] | None = None,
    max_queries: int | None = None,
    seed: int = 12345,
) -> dict[str, Any]:
    """Convert local MTEB/Hugging Face-style MemBench qrels to a dry-run report."""

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
    source = _find_source_files(root, manifest)
    corpus_records, duplicate_doc_ids = _load_corpus(source.corpus_path)
    queries = _load_queries(source.queries_path)
    qrels = _load_qrels(source.qrels_path)

    corpus_manifest, doc_to_experience = _build_corpus_manifest(
        corpus_records, manifest=manifest
    )
    source_fixture_base = _fixture_base(
        corpus_records=corpus_records,
        corpus_manifest=corpus_manifest,
        source=source,
        manifest=manifest,
    )

    skipped_examples: list[dict[str, Any]] = []
    fixture_previews = []
    leakage_results = []
    selected_count = 0
    grouped_qrels = _group_qrels(qrels)

    for query_id in sorted(grouped_qrels):
        if max_queries is not None and selected_count >= max_queries:
            break
        query = queries.get(query_id)
        query_qrels = grouped_qrels[query_id]
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
        leakage.extend(find_label_leakage(views.adapter_view))
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
                "query_id_hash": stable_hash(query_id),
                "source_fixture_experience_namespace": "exp_src_*",
                "adapter_view": views.adapter_view,
                "scorer_view": views.scorer_view,
                "fixture_public_hash": views.fixture_public_hash,
                "fixture_gold_hash": views.fixture_gold_hash,
                "fixture_full_hash": views.fixture_full_hash,
                "hash_sensitivity": _hash_sensitivity(
                    fixture, fixture_ordinal=request_index, seed=seed
                ),
                "leakage_failure_count": len(leakage),
            }
        )
        selected_count += 1

    report = {
        "schema_version": DRY_RUN_SCHEMA_VERSION,
        "converter": {
            "converter_id": CONVERTER_ID,
            "converter_version": CONVERTER_VERSION,
        },
        "source_manifest": manifest,
        "source_files": _source_file_manifest(source),
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
            "queries": len(queries),
            "qrel_rows": len(qrels),
            "grouped_qrel_queries": len(grouped_qrels),
            "selected_fixture_previews": len(fixture_previews),
            "skipped_examples": len(skipped_examples),
            "duplicate_doc_ids": len(duplicate_doc_ids),
        },
        "qrel_mapping": {
            "success_count": len(fixture_previews),
            "skipped_count": len(skipped_examples),
            "duplicate_doc_ids": sorted(duplicate_doc_ids),
            "corpus_manifest_hash": stable_hash(corpus_manifest),
            "corpus_manifest": corpus_manifest,
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
            "experience_items_per_fixture": len(corpus_records),
            "default_k": 5,
            "max_evidence_items": 5,
        },
        "fixture_previews": fixture_previews,
        "commit_policy": {
            "raw_source_committed": False,
            "generated_fixture_pack_committed": False,
            "dry_run_artifact_policy": "local_only_unless_source_audit_commit_allowed",
        },
    }
    report["dry_run_hash"] = stable_hash(
        {key: value for key, value in report.items() if key != "dry_run_hash"}
    )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    audit_parser = subcommands.add_parser("audit-source")
    audit_parser.add_argument("source_dir")
    audit_parser.add_argument("--manifest")
    audit_parser.add_argument("--source-revision")
    audit_parser.add_argument("--source-subset", action="append")
    audit_parser.add_argument("--declared-license")
    audit_parser.add_argument("--license-source")
    audit_parser.add_argument("--citation-target", action="append")
    audit_parser.add_argument("--redistribution-status", default="private_only")
    audit_parser.add_argument("--output", required=True)

    dry_run_parser = subcommands.add_parser("dry-run-mteb-qrels")
    dry_run_parser.add_argument("source_dir")
    dry_run_parser.add_argument("--manifest")
    dry_run_parser.add_argument("--source-revision")
    dry_run_parser.add_argument("--source-subset", action="append")
    dry_run_parser.add_argument("--max-queries", type=int)
    dry_run_parser.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command == "audit-source":
        manifest = audit_mteb_source_manifest(
            args.source_dir,
            manifest_path=args.manifest,
            source_revision=args.source_revision,
            source_subset=args.source_subset,
            declared_license=args.declared_license,
            license_source=args.license_source,
            citation_targets=args.citation_target,
            redistribution_status=args.redistribution_status,
        )
        write_json_artifact(args.output, manifest)
        return 0

    report = convert_mteb_qrels_dry_run(
        args.source_dir,
        manifest_path=args.manifest,
        source_revision=args.source_revision,
        source_subset=args.source_subset,
        max_queries=args.max_queries,
    )
    write_json_artifact(args.output, report)
    return 0


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
