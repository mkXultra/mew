from __future__ import annotations

from pathlib import Path
import hashlib
import json
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .memory_core import (
    InMemoryMemoryStore,
    JsonFileMemoryStore,
    MemoryChainRequest,
    MemoryEntry,
    MemoryInspectRequest,
    MemoryRecallBudget,
    MemoryRecallRequest,
    MemorySystem,
)


MEMORY_MODES = ("memory_off", "memory_on", "stale")


def stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json_file(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_entries_from_payload(payload: Any) -> Tuple[MemoryEntry, ...]:
    raw_entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(raw_entries, list):
        return ()
    return tuple(MemoryEntry.from_dict(item) for item in raw_entries if isinstance(item, dict))


def build_memory_system_from_store_path(store_path: Optional[str]) -> MemorySystem:
    if not store_path:
        return MemorySystem(InMemoryMemoryStore())
    return MemorySystem(JsonFileMemoryStore(Path(store_path)))


def build_memory_system_from_entries(entries: Sequence[MemoryEntry], *, store_id: str) -> MemorySystem:
    return MemorySystem(
        InMemoryMemoryStore(
            tuple(entries),
            store_id=store_id,
            index_id=f"{store_id}:index:{memory_snapshot_hash(entries)[:16]}",
        )
    )


def memory_snapshot_hash(entries: Sequence[MemoryEntry]) -> str:
    return stable_payload_hash({"entries": [entry.to_dict() for entry in entries]})


def recall_config_hash(config: Mapping[str, Any]) -> str:
    return stable_payload_hash(dict(config))


def recall_artifact(
    *,
    store_path: Optional[str],
    query: str,
    scope: str = "",
    memory_kinds: Sequence[str] = (),
    limit: int = 5,
    include_stale: bool = False,
) -> Dict[str, Any]:
    system = build_memory_system_from_store_path(store_path)
    request = MemoryRecallRequest(
        query=query,
        scope=scope,
        memory_kinds=tuple(memory_kinds),
        limit=limit,
        include_stale=include_stale,
        budget=MemoryRecallBudget(max_results=limit),
    )
    result = system.recall(request)
    result_data = result.to_dict()
    metrics = memory_result_metrics(result_data)
    artifact = {
        "operation": "recall",
        "store_path": store_path or "",
        "query": query,
        "scope": scope,
        "memory_kinds": list(memory_kinds),
        "include_stale": include_stale,
        "recall_config_hash": recall_config_hash(request.to_dict()),
        "result": result_data,
        "metrics": metrics,
        "debug_trace": recall_debug_trace(result_data, metrics),
    }
    artifact["summary"] = format_recall_summary(artifact)
    return artifact


def chain_artifact(
    *,
    store_path: Optional[str],
    entry_ids: Sequence[str],
    max_depth: int = 1,
    max_fanout: int = 5,
    max_nodes: int = 20,
    max_chars: int = 4000,
    edge_kinds: Sequence[str] = (),
    include_stale: bool = False,
) -> Dict[str, Any]:
    system = build_memory_system_from_store_path(store_path)
    request = MemoryChainRequest(
        start_entry_ids=tuple(entry_ids),
        max_depth=max_depth,
        max_fanout=max_fanout,
        max_nodes=max_nodes,
        max_chars=max_chars,
        edge_kinds=tuple(edge_kinds),
        include_stale=include_stale,
    )
    result = system.expand_chain(request)
    artifact = {
        "operation": "chain",
        "store_path": store_path or "",
        "entry_ids": list(entry_ids),
        "chain_config_hash": recall_config_hash(request.to_dict()),
        "result": result.to_dict(),
        "metrics": chain_result_metrics(result.to_dict()),
    }
    artifact["summary"] = format_chain_summary(artifact)
    return artifact


def inspect_artifact(*, store_path: Optional[str], entry_id: str) -> Dict[str, Any]:
    system = build_memory_system_from_store_path(store_path)
    result = system.inspect_entry(MemoryInspectRequest(entry_id=entry_id))
    artifact = {
        "operation": "inspect",
        "store_path": store_path or "",
        "entry_id": entry_id,
        "result": result.to_dict(),
    }
    artifact["summary"] = format_inspect_summary(artifact)
    return artifact


def score_fixture_artifact(*, fixture_path: str, mode: str) -> Dict[str, Any]:
    if mode not in MEMORY_MODES:
        raise ValueError(f"memory mode must be one of: {', '.join(MEMORY_MODES)}")
    fixture = read_json_file(Path(fixture_path))
    entries = entries_for_mode(fixture, mode)
    system = build_memory_system_from_entries(entries, store_id=f"memory:fixture:{mode}")
    query = str(fixture.get("query") or "")
    memory_kinds = tuple(fixture.get("memory_kinds") or ())
    scope = str(fixture.get("scope") or "")
    limit = int(fixture.get("limit") or 5)
    request = MemoryRecallRequest(
        query=query,
        scope=scope,
        memory_kinds=memory_kinds,
        limit=limit,
        include_stale=bool(fixture.get("include_stale", False)),
        budget=MemoryRecallBudget(max_results=limit),
    )
    result = system.recall(request)
    result_data = result.to_dict()
    expected = tuple(str(item) for item in fixture.get("expected_entry_ids") or ())
    metrics = memory_result_metrics(result_data, expected_entry_ids=expected)
    artifact = {
        "operation": "score",
        "fixture_path": fixture_path,
        "memory_mode": mode,
        "fixture_boundary": {
            "memory_arena_style": True,
            "harbor_resident_memory": True,
            "direct_memory_system": True,
            "model_used": False,
        },
        "task_family": str(fixture.get("task_family") or "memory_core"),
        "task_id": str(fixture.get("task_id") or Path(fixture_path).stem),
        "phase_or_session": str(fixture.get("phase_or_session") or ""),
        "store_id": system.store.store_id,
        "memory_snapshot_hash": memory_snapshot_hash(entries),
        "recall_config_hash": recall_config_hash(request.to_dict()),
        "model_or_runner_config_hash": "direct-memory-core-no-model",
        "result": result_data,
        "metrics": metrics,
        "debug_trace": recall_debug_trace(result_data, metrics),
    }
    artifact["summary"] = format_score_summary(artifact)
    return artifact


def entries_for_mode(fixture: Mapping[str, Any], mode: str) -> Tuple[MemoryEntry, ...]:
    if mode == "memory_off":
        return ()
    if mode == "stale" and "stale_entries" not in fixture:
        raise ValueError("stale memory mode requires explicit stale_entries")
    key = "stale_entries" if mode == "stale" else "entries"
    entries = load_entries_from_payload({"entries": fixture.get(key) or []})
    return entries


def memory_result_metrics(
    result: Mapping[str, Any],
    *,
    expected_entry_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    candidates = list(result.get("candidates") or [])
    candidate_ids = [str(item.get("entry_id") or "") for item in candidates]
    expected = tuple(expected_entry_ids)
    hits = [entry_id for entry_id in candidate_ids if entry_id in expected] if expected else []
    stale_hits = [
        item
        for item in candidates
        if ((item.get("staleness") or {}).get("state") in {"stale", "superseded"})
    ]
    contradiction_hits = [
        item
        for item in candidates
        if ((item.get("contradiction") or {}).get("state") in {"possible", "contradicted"})
    ]
    budget = result.get("budget_used") or {}
    trace = result.get("trace") or {}
    return {
        "candidate_entry_ids": candidate_ids,
        "returned_entry_ids": candidate_ids,
        "evidence_hits": hits,
        "evidence_hit_count": len(hits),
        "expected_entry_ids": list(expected),
        "expected_hit_count": len([entry_id for entry_id in expected if entry_id in candidate_ids]),
        "recall_at_k": bool(expected and any(entry_id in candidate_ids for entry_id in expected)),
        "stale_recall_count": len(stale_hits),
        "contradiction_count": len(contradiction_hits),
        "dropped_reasons": dict(result.get("dropped") or {}),
        "latency_ms": float(result.get("timing_ms") or trace.get("timing_ms") or 0.0),
        "returned_chars": int(budget.get("returned_chars") or 0),
        "returned_results": int(budget.get("returned_results") or 0),
        "store_reads": int(budget.get("store_reads") or 0),
        "trace_ref": str(result.get("trace_ref") or ""),
    }


def recall_debug_trace(result: Mapping[str, Any], metrics: Mapping[str, Any]) -> Dict[str, Any]:
    trace = result.get("trace") or {}
    return {
        "trace_ref": str(result.get("trace_ref") or trace.get("trace_ref") or ""),
        "request_hash": str(trace.get("request_hash") or ""),
        "result_hash": str(trace.get("result_hash") or ""),
        "store_id": str(trace.get("store_id") or ""),
        "index_id": str(trace.get("index_id") or ""),
        "evidence_hits": list(metrics.get("evidence_hits") or []),
        "dropped_reasons": dict(metrics.get("dropped_reasons") or {}),
        "stale_recall_count": int(metrics.get("stale_recall_count") or 0),
        "contradiction_count": int(metrics.get("contradiction_count") or 0),
        "latency_ms": float(metrics.get("latency_ms") or 0.0),
        "returned_chars": int(metrics.get("returned_chars") or 0),
        "returned_results": int(metrics.get("returned_results") or 0),
        "store_reads": int(metrics.get("store_reads") or 0),
    }


def chain_result_metrics(result: Mapping[str, Any]) -> Dict[str, Any]:
    nodes = list(result.get("nodes") or [])
    edges = list(result.get("edges") or [])
    budget = result.get("budget_used") or {}
    return {
        "node_entry_ids": [str(item.get("entry_id") or "") for item in nodes],
        "edge_ids": [str(item.get("edge_id") or "") for item in edges],
        "dropped_reasons": dict(result.get("dropped") or {}),
        "latency_ms": float(result.get("timing_ms") or 0.0),
        "returned_chars": int(budget.get("returned_chars") or 0),
        "returned_results": int(budget.get("returned_results") or 0),
        "store_reads": int(budget.get("store_reads") or 0),
        "trace_ref": str(result.get("trace_ref") or ""),
    }


def format_recall_summary(artifact: Mapping[str, Any]) -> str:
    metrics = artifact.get("metrics") or {}
    dropped = metrics.get("dropped_reasons") or {}
    return (
        f"memory recall: hits={metrics.get('evidence_hit_count', 0)} "
        f"returned={metrics.get('returned_results', 0)} "
        f"chars={metrics.get('returned_chars', 0)} "
        f"latency_ms={metrics.get('latency_ms', 0):.3f} "
        f"dropped={dropped}"
    )


def format_chain_summary(artifact: Mapping[str, Any]) -> str:
    metrics = artifact.get("metrics") or {}
    dropped = metrics.get("dropped_reasons") or {}
    return (
        f"memory chain: nodes={len(metrics.get('node_entry_ids') or [])} "
        f"edges={len(metrics.get('edge_ids') or [])} "
        f"latency_ms={metrics.get('latency_ms', 0):.3f} "
        f"dropped={dropped}"
    )


def format_inspect_summary(artifact: Mapping[str, Any]) -> str:
    result = artifact.get("result") or {}
    entry = result.get("entry")
    if not entry:
        return f"memory inspect: entry not found or not recallable dropped={result.get('dropped') or {}}"
    return f"memory inspect: {entry.get('entry_id')} kind={entry.get('memory_kind')} scope={entry.get('scope')}"


def format_score_summary(artifact: Mapping[str, Any]) -> str:
    metrics = artifact.get("metrics") or {}
    return (
        f"memory score: mode={artifact.get('memory_mode')} "
        f"task={artifact.get('task_id')} "
        f"expected_hits={metrics.get('expected_hit_count', 0)} "
        f"recall_at_k={metrics.get('recall_at_k')} "
        f"dropped={metrics.get('dropped_reasons') or {}}"
    )


def write_artifact(path: Optional[str], artifact: Mapping[str, Any]) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_artifact_summary(artifact: Mapping[str, Any]) -> str:
    return str(artifact.get("summary") or "")
