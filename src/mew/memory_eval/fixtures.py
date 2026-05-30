"""Fixture loading, public/scorer split, and label-leak checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .artifacts import make_failure
from .hashing import stable_hash


FIXTURE_SCHEMA_VERSION = "memory_eval_fixture.v1"

REQUEST_SCORER_KEYS = {
    "mode",
    "requires_capabilities",
    "on_unsupported",
    "gold",
    "expected_failure_types",
}

EXPERIENCE_PUBLIC_KEYS = {
    "experience_id",
    "scope_id",
    "session_id",
    "turn_id",
    "event_time",
    "ingest_order",
    "actor_id",
    "payload",
    "visibility",
    "metadata",
}

MUTATION_PUBLIC_KEYS = {
    "op_id",
    "mutation_type",
    "target_experience_id",
    "replacement_experience_id",
    "effective_time",
    "reason",
    "graph",
}

REQUEST_PUBLIC_KEYS = {
    "scope_id",
    "query_time",
    "query",
    "k",
    "filters",
    "budget",
}

BLOCKED_TOKENS = {
    "gold",
    "mode",
    "family",
    "relevant",
    "must_not",
    "expected",
    "stale_evidence_ids",
    "conflict_sets",
    "memory_off",
    "memory_on",
    "scope_isolation",
    "stale_conflict",
    "update_forget",
    "abstention",
    "budget_limited",
    "trap",
    "leak",
    "forbidden",
    "stale",
    "conflict",
}


@dataclass(frozen=True)
class FixtureViews:
    source: dict[str, Any]
    source_path: str | None
    fixture_id: str
    adapter_fixture_id: str
    fixture_version: str
    evaluation_time: str
    adapter_view: dict[str, Any]
    scorer_view: dict[str, Any]
    id_maps: dict[str, dict[str, str]]
    fixture_public_hash: str
    fixture_gold_hash: str
    fixture_full_hash: str


def load_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    with fixture_path.open("r", encoding="utf-8") as handle:
        fixture = json.load(handle)
    fixture["_source_path"] = str(fixture_path)
    return fixture


def split_fixture(
    fixture: Mapping[str, Any],
    *,
    fixture_ordinal: int = 1,
    seed: int = 12345,
) -> FixtureViews:
    source = dict(fixture)
    source_path = source.pop("_source_path", None)
    fixture_id = str(source.get("fixture_id") or f"fixture_{fixture_ordinal:06d}")
    fixture_version = str(source.get("fixture_version") or "1.0.0")
    evaluation_time = str(source.get("evaluation_time") or "2026-05-21T00:00:00Z")
    adapter_fixture_id = f"fx_{fixture_ordinal:06d}"
    source_experiences = list(source.get("experiences") or [])
    source_mutations = list(source.get("mutations") or [])

    experience_id_map = {
        str(item.get("experience_id")): f"ex_{index:06d}"
        for index, item in enumerate(source_experiences, start=1)
        if item.get("experience_id")
    }
    mutation_id_map = {
        str(item.get("op_id")): f"mu_{index:06d}"
        for index, item in enumerate(source_mutations, start=1)
        if item.get("op_id")
    }

    request_id_map: dict[str, str] = {}
    requests_public = []
    requests_scorer = []
    for index, request in enumerate(source.get("requests") or [], start=1):
        request_id = str(request.get("request_id") or f"request_{index:06d}")
        adapter_request_id = f"rq_{index:06d}"
        request_id_map[request_id] = adapter_request_id

        public_request = {key: _copy_json(request.get(key)) for key in REQUEST_PUBLIC_KEYS if key in request}
        public_request["request_id"] = adapter_request_id
        requests_public.append(public_request)

        scorer_request = {
            "request_id": request_id,
            "adapter_request_id": adapter_request_id,
            "scope_id": request.get("scope_id"),
            "mode": request.get("mode"),
            "requires_capabilities": list(request.get("requires_capabilities") or []),
            "on_unsupported": request.get("on_unsupported") or "hard_failure",
            "gold": _copy_json(request.get("gold") or {}),
            "expected_failure_types": list(request.get("expected_failure_types") or []),
        }
        requests_scorer.append(scorer_request)

    experiences_public = [_public_experience(item, experience_id_map) for item in source_experiences]
    mutations_public = [_public_mutation(item, experience_id_map, mutation_id_map) for item in source_mutations]

    operation_sequence_public = []
    operation_sequence_scorer = []
    for operation in source.get("operation_sequence") or []:
        public_operation = dict(operation)
        scorer_operation = dict(operation)
        if public_operation.get("type") == "ingest":
            original_experience_id = str(public_operation.get("experience_id") or "")
            public_operation["experience_id"] = experience_id_map.get(original_experience_id, original_experience_id)
        elif public_operation.get("type") == "mutate":
            original_op_id = str(public_operation.get("op_id") or "")
            public_operation["op_id"] = mutation_id_map.get(original_op_id, original_op_id)
        elif public_operation.get("type") == "request":
            original_request_id = str(public_operation.get("request_id") or "")
            public_operation["request_id"] = request_id_map.get(original_request_id, original_request_id)
            public_operation.pop("after_ingest_order", None)
        operation_sequence_public.append(public_operation)
        operation_sequence_scorer.append(scorer_operation)

    adapter_view = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture_id": adapter_fixture_id,
        "fixture_version": fixture_version,
        "evaluation_time": evaluation_time,
        "seed": seed,
        "experiences": experiences_public,
        "mutations": mutations_public,
        "requests": requests_public,
        "operation_sequence": operation_sequence_public,
    }
    scorer_view = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "fixture_version": fixture_version,
        "phase": source.get("phase") or "P0",
        "fixture_family": source.get("fixture_family"),
        "evaluation_time": evaluation_time,
        "experiences": _copy_json(source.get("experiences") or []),
        "mutations": _copy_json(source.get("mutations") or []),
        "requests": requests_scorer,
        "operation_sequence": operation_sequence_scorer,
    }
    if "source_benchmark" in source:
        scorer_view["source_benchmark"] = _copy_json(source.get("source_benchmark") or {})

    return FixtureViews(
        source=dict(source),
        source_path=source_path,
        fixture_id=fixture_id,
        adapter_fixture_id=adapter_fixture_id,
        fixture_version=fixture_version,
        evaluation_time=evaluation_time,
        adapter_view=adapter_view,
        scorer_view=scorer_view,
        id_maps={
            "request_id_to_adapter": request_id_map,
            "adapter_request_id_to_scorer": {value: key for key, value in request_id_map.items()},
            "experience_id_to_adapter": experience_id_map,
            "adapter_experience_id_to_scorer": {value: key for key, value in experience_id_map.items()},
            "mutation_id_to_adapter": mutation_id_map,
            "adapter_mutation_id_to_scorer": {value: key for key, value in mutation_id_map.items()},
        },
        fixture_public_hash=stable_hash(adapter_view),
        fixture_gold_hash=stable_hash(scorer_view),
        fixture_full_hash=stable_hash(source),
    )


def find_label_leakage(
    adapter_view: Mapping[str, Any],
    *,
    blocked_tokens: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    source_tokens = BLOCKED_TOKENS if blocked_tokens is None else blocked_tokens
    blocked = {_normalize_token(token) for token in source_tokens}
    failures = []
    for path, value in _walk(adapter_view):
        if isinstance(value, str):
            haystack = _normalize_token(value)
            matched = _matched_token(haystack, blocked)
        else:
            matched = None
        key_match = _matched_token(_normalize_token(path.split(".")[-1]), blocked)
        if matched or key_match:
            token = matched or key_match
            failures.append(
                make_failure(
                    stage="artifact",
                    type="label_leakage",
                    message=f"Adapter view contains blocked token {token!r} at {path}.",
                    gate_id="no_label_leakage",
                    expected="no blocked scorer tokens in adapter view",
                    actual={"path": path, "token": token},
                )
            )
    return failures


def reset_payload(
    views: FixtureViews,
    *,
    run_id: str,
    seed: int = 12345,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "fixture_id": views.adapter_fixture_id,
        "fixture_public_hash": views.fixture_public_hash,
        "seed": seed,
        "evaluation_time": views.evaluation_time,
    }


def _matched_token(haystack: str, blocked: set[str]) -> str | None:
    for token in sorted(blocked, key=len, reverse=True):
        if token and token in haystack:
            return token
    return None


def _normalize_token(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _walk(value: Any, path: str = "$"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, key
            yield from _walk(child, child_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")
        return
    yield path, value


def _copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _public_experience(item: Mapping[str, Any], experience_id_map: Mapping[str, str]) -> dict[str, Any]:
    public = {key: _copy_json(item.get(key)) for key in EXPERIENCE_PUBLIC_KEYS if key in item}
    original_id = str(item.get("experience_id") or "")
    if original_id in experience_id_map:
        public["experience_id"] = experience_id_map[original_id]
    return public


def _public_mutation(
    item: Mapping[str, Any],
    experience_id_map: Mapping[str, str],
    mutation_id_map: Mapping[str, str],
) -> dict[str, Any]:
    public = {key: _copy_json(item.get(key)) for key in MUTATION_PUBLIC_KEYS if key in item}
    original_op_id = str(item.get("op_id") or "")
    if original_op_id in mutation_id_map:
        public["op_id"] = mutation_id_map[original_op_id]
    for key in ("target_experience_id", "replacement_experience_id"):
        if key in public:
            original_experience_id = str(public.get(key) or "")
            public[key] = experience_id_map.get(original_experience_id, original_experience_id)
    if "graph" in public:
        public["graph"] = _rewrite_graph_experience_ids(public["graph"], experience_id_map)
    return public


def _rewrite_graph_experience_ids(value: Any, experience_id_map: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        rewritten = {}
        for key, child in value.items():
            if key in {
                "experience_id",
                "from_experience_id",
                "to_experience_id",
                "card_experience_id",
                "support_experience_id",
                "evidence_experience_id",
            }:
                original = str(child or "")
                rewritten[key] = experience_id_map.get(original, original)
            elif key == "experience_ids" and isinstance(child, list):
                rewritten[key] = [experience_id_map.get(str(item), str(item)) for item in child]
            else:
                rewritten[key] = _rewrite_graph_experience_ids(child, experience_id_map)
        return rewritten
    if isinstance(value, list):
        return [_rewrite_graph_experience_ids(item, experience_id_map) for item in value]
    return value
