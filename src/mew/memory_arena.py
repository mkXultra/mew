from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import statistics
import time
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from .memory_core import (
    InMemoryMemoryStore,
    MemoryEntry,
    MemoryRecallBudget,
    MemoryRecallRequest,
    MemorySystem,
    ProvenanceRef,
    Staleness,
)
from .memory_debug import (
    MEMORY_MODES,
    memory_result_metrics,
    memory_snapshot_hash,
    recall_config_hash,
    recall_debug_trace,
    stable_payload_hash,
)


MEMORY_ARENA_DATASET = "ZexueHe/memoryarena"


@dataclass(frozen=True)
class ArenaRow:
    row_id: str
    task_family: str
    background: str
    questions: Tuple[str, ...]
    answers: Tuple[str, ...]
    raw: Mapping[str, Any]


def load_memory_arena_rows(
    *,
    input_path: Optional[str] = None,
    hf_config: Optional[str] = None,
    hf_split: str = "test",
    hf_revision: Optional[str] = None,
    limit_rows: int = 0,
) -> Tuple[ArenaRow, ...]:
    if input_path:
        rows = tuple(_arena_rows_from_payload(read_json_or_jsonl(Path(input_path)), source_id=Path(input_path).stem))
    else:
        rows = tuple(
            _arena_rows_from_payload(
                _load_hf_memory_arena_rows(
                    hf_config=hf_config,
                    hf_split=hf_split,
                    hf_revision=hf_revision,
                    limit_rows=limit_rows,
                ),
                source_id=hf_config or "memoryarena",
            )
        )
    if limit_rows > 0:
        return rows[:limit_rows]
    return rows


def read_json_or_jsonl(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("[") or stripped.startswith("{"):
        return json.loads(stripped)
    return [json.loads(line) for line in stripped.splitlines() if line.strip()]


def _load_hf_memory_arena_rows(
    *,
    hf_config: Optional[str],
    hf_split: str,
    hf_revision: Optional[str],
    limit_rows: int,
) -> List[Mapping[str, Any]]:
    if not hf_config:
        raise ValueError("memory-arena-score requires --input or --hf-config")
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as exc:
        raise ValueError(
            "Hugging Face dataset loading requires the optional 'datasets' package; "
            "rerun with a local --input export or an environment that has datasets installed"
        ) from exc
    kwargs: Dict[str, Any] = {}
    if hf_revision:
        kwargs["revision"] = hf_revision
    dataset = load_dataset(MEMORY_ARENA_DATASET, hf_config, split=hf_split, **kwargs)
    raw_rows: List[Mapping[str, Any]] = []
    for index, item in enumerate(dataset):
        if limit_rows > 0 and index >= limit_rows:
            break
        if isinstance(item, Mapping):
            raw_rows.append(item)
    return raw_rows


def _arena_rows_from_payload(payload: Any, *, source_id: str) -> Iterator[ArenaRow]:
    if isinstance(payload, Mapping):
        if "rows" in payload:
            raw_rows = payload.get("rows")
        elif any(key in payload for key in ("questions", "question_list", "subtasks", "sessions", "queries")):
            raw_rows = [payload]
        else:
            raw_rows = payload.get("data") or []
    else:
        raw_rows = payload
    if isinstance(raw_rows, Mapping):
        if any(key in raw_rows for key in ("questions", "question_list", "subtasks", "sessions", "queries")):
            raw_rows = [raw_rows]
        else:
            raw_rows = raw_rows.get("data") or raw_rows.get("rows") or []
    if not isinstance(raw_rows, list):
        return
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            continue
        row = arena_row_from_mapping(raw, fallback_id=f"{source_id}:{index}")
        if row:
            yield row


def arena_row_from_mapping(raw: Mapping[str, Any], *, fallback_id: str) -> Optional[ArenaRow]:
    questions = _string_sequence(
        _first_present(
            raw,
            (
                "questions",
                "question_list",
                "subtasks",
                "sessions",
                "queries",
                "turns",
                "tasks",
            ),
        )
    )
    answers = _string_sequence(
        _first_present(raw, ("answers", "answer_list", "targets", "responses", "expected_answers"))
    )
    if len(questions) < 2:
        return None
    if not answers:
        answers = tuple("" for _ in questions)
    if len(answers) < len(questions):
        answers = answers + tuple("" for _ in range(len(questions) - len(answers)))
    background = _text_from_value(
        _first_present(raw, ("background", "context", "scenario", "profile", "memory", "shared_context"))
    )
    row_id = _clean_id(str(_first_present(raw, ("id", "task_id", "uid", "uuid")) or fallback_id))
    task_family = str(_first_present(raw, ("task_family", "category", "config", "domain")) or "memoryarena")
    return ArenaRow(
        row_id=row_id,
        task_family=task_family,
        background=background,
        questions=tuple(questions),
        answers=tuple(answers[: len(questions)]),
        raw=raw,
    )


def _first_present(raw: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _string_sequence(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        value = value.get("items") or value.get("turns") or value.get("questions") or value.get("data")
    if not isinstance(value, Iterable):
        return (_text_from_value(value),)
    items: List[str] = []
    for item in value:
        text = _text_from_value(item)
        if text:
            items.append(text)
    return tuple(items)


def _text_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, Mapping):
        for key in ("question", "query", "task", "instruction", "answer", "target", "content", "text"):
            if key in value and value[key] not in (None, ""):
                return _text_from_value(value[key])
        return " ".join(_text_from_value(value.get(key, "")) for key in sorted(value)).strip()
    if isinstance(value, list):
        return " ".join(_text_from_value(item) for item in value).strip()
    return " ".join(str(value).strip().split())


def _clean_id(value: str) -> str:
    cleaned = []
    for char in value.strip():
        cleaned.append(char if char.isalnum() or char in {"_", "-", ":", "."} else "-")
    return "".join(cleaned).strip("-") or "memoryarena-row"


def score_memory_arena_artifact(
    *,
    input_path: Optional[str] = None,
    hf_config: Optional[str] = None,
    hf_split: str = "test",
    hf_revision: Optional[str] = None,
    mode: str,
    limit_rows: int = 0,
    limit: int = 5,
    include_stale: bool = False,
) -> Dict[str, Any]:
    if mode not in MEMORY_MODES:
        raise ValueError(f"memory mode must be one of: {', '.join(MEMORY_MODES)}")
    rows = load_memory_arena_rows(
        input_path=input_path,
        hf_config=hf_config,
        hf_split=hf_split,
        hf_revision=hf_revision,
        limit_rows=limit_rows,
    )
    started = time.perf_counter()
    row_results: List[Dict[str, Any]] = []
    for row in rows:
        row_results.extend(
            score_memory_arena_row(
                row,
                mode=mode,
                limit=limit,
                include_stale=include_stale,
            )
        )
    aggregate = aggregate_arena_results(row_results)
    artifact = {
        "operation": "memory_arena_score",
        "dataset": MEMORY_ARENA_DATASET if hf_config else "",
        "input_path": input_path or "",
        "hf_config": hf_config or "",
        "hf_split": hf_split,
        "hf_revision": hf_revision or "",
        "memory_mode": mode,
        "limit_rows": limit_rows,
        "rows_loaded": len(rows),
        "queries_scored": len(row_results),
        "runner_boundary": {
            "memory_arena_style": True,
            "direct_memory_system": True,
            "implement_v2_used": False,
            "model_used": False,
            "production_prompt_injection": False,
        },
        "runner_config_hash": stable_payload_hash(
            {
                "input_path": input_path or "",
                "hf_config": hf_config or "",
                "hf_split": hf_split,
                "hf_revision": hf_revision or "",
                "mode": mode,
                "limit_rows": limit_rows,
                "limit": limit,
                "include_stale": include_stale,
            }
        ),
        "aggregate": aggregate,
        "row_results": row_results,
        "timing_ms": (time.perf_counter() - started) * 1000.0,
    }
    artifact["summary"] = format_memory_arena_summary(artifact)
    return artifact


def score_memory_arena_row(
    row: ArenaRow,
    *,
    mode: str,
    limit: int,
    include_stale: bool,
) -> Tuple[Dict[str, Any], ...]:
    results: List[Dict[str, Any]] = []
    for subtask_index in range(1, len(row.questions)):
        entries = arena_entries_for_mode(row, mode=mode, before_index=subtask_index)
        system = MemorySystem(
            InMemoryMemoryStore(
                tuple(entries),
                store_id=f"memoryarena:{row.task_family}:{row.row_id}:{mode}:{subtask_index}",
                index_id=f"memoryarena:index:{row.row_id}:{mode}:{subtask_index}",
            )
        )
        request = MemoryRecallRequest(
            query=arena_query(row, subtask_index),
            scope=f"memoryarena:{row.task_family}:{row.row_id}",
            memory_kinds=("episodic_task",),
            limit=limit,
            include_stale=include_stale,
            budget=MemoryRecallBudget(max_results=limit),
        )
        result = system.recall(request)
        result_data = result.to_dict()
        expected_ids = tuple(entry.entry_id for entry in entries if entry.staleness.state == "fresh")
        metrics = memory_result_metrics(result_data, expected_entry_ids=expected_ids)
        results.append(
            {
                "task_family": row.task_family,
                "task_id": row.row_id,
                "subtask_index": subtask_index,
                "memory_mode": mode,
                "query": request.query,
                "expected_entry_ids": list(expected_ids),
                "memory_snapshot_hash": memory_snapshot_hash(entries),
                "recall_config_hash": recall_config_hash(request.to_dict()),
                "metrics": metrics,
                "debug_trace": recall_debug_trace(result_data, metrics),
                "result": result_data,
            }
        )
    return tuple(results)


def arena_query(row: ArenaRow, subtask_index: int) -> str:
    parts = [row.background, arena_step_text(row.questions[subtask_index])]
    return "\n".join(part for part in parts if part)


def arena_step_text(question: str) -> str:
    separator = "----------------------------------------------------------------"
    if separator in question:
        return " ".join(question.rsplit(separator, 1)[-1].strip().split())
    return " ".join(question.strip().split())


def arena_entries_for_mode(row: ArenaRow, *, mode: str, before_index: int) -> Tuple[MemoryEntry, ...]:
    if mode == "memory_off":
        return ()
    stale = mode == "stale"
    entries: List[MemoryEntry] = []
    for index in range(before_index):
        answer = row.answers[index] if index < len(row.answers) else ""
        question = row.questions[index]
        entry_id = f"arena:{row.row_id}:session:{index}"
        payload = {
            "row_id": row.row_id,
            "question": question,
            "answer": answer,
            "index": index,
        }
        source_ref = ProvenanceRef(
            ref_id=f"{entry_id}:source",
            ref_kind="memoryarena_subtask",
            artifact_path_or_uri=f"memoryarena://{row.row_id}/{index}",
            content_hash=f"sha256:{stable_payload_hash(payload)}",
            producer="memory_arena_adapter",
        )
        proof_ref = ProvenanceRef(
            ref_id=f"{entry_id}:answer",
            ref_kind="memoryarena_answer",
            artifact_path_or_uri=f"memoryarena://{row.row_id}/{index}/answer",
            content_hash=f"sha256:{stable_payload_hash({'answer': answer})}",
            producer="memory_arena_adapter",
        )
        staleness = (
            Staleness(state="stale", reasons=("memory_arena_stale_mode",), invalidators=(source_ref,))
            if stale
            else Staleness()
        )
        entries.append(
            MemoryEntry(
                entry_id=entry_id,
                memory_kind="episodic_task",
                scope=f"memoryarena:{row.task_family}:{row.row_id}",
                title=f"MemoryArena session {index}",
                summary=f"Question: {arena_step_text(question)}\nAnswer: {answer}",
                applicability=f"Use for later MemoryArena subtasks in row {row.row_id}.",
                source_refs=(source_ref,),
                proof_refs=(proof_ref,),
                created_at="2026-05-20T00:00:00Z",
                last_verified_at="2026-05-20T00:00:00Z",
                validity="valid",
                confidence=1.0,
                staleness=staleness,
            )
        )
    return tuple(entries)


def aggregate_arena_results(row_results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    expected_rows = [
        item
        for item in row_results
        if (item.get("metrics") or {}).get("expected_entry_ids")
    ]
    hit_rows = [
        item
        for item in expected_rows
        if int((item.get("metrics") or {}).get("expected_hit_count") or 0) > 0
    ]
    stale_as_fresh = 0
    latencies = []
    returned_chars = []
    for item in row_results:
        metrics = item.get("metrics") or {}
        stale_as_fresh += int(metrics.get("stale_recall_count") or 0)
        latencies.append(float(metrics.get("latency_ms") or 0.0))
        returned_chars.append(int(metrics.get("returned_chars") or 0))
    return {
        "expected_rows": len(expected_rows),
        "evidence_hit_rows": len(hit_rows),
        "recall_at_k": (len(hit_rows) / len(expected_rows)) if expected_rows else 0.0,
        "stale_as_fresh_count": stale_as_fresh,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
        "returned_chars_p95": _percentile(returned_chars, 95),
        "queries_scored": len(row_results),
    }


def _percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(float(value) for value in values)
    if percentile == 50:
        return float(statistics.median(sorted_values))
    rank = (len(sorted_values) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def format_memory_arena_summary(artifact: Mapping[str, Any]) -> str:
    aggregate = artifact.get("aggregate") or {}
    return (
        f"memory arena score: mode={artifact.get('memory_mode')} "
        f"rows={artifact.get('rows_loaded')} queries={artifact.get('queries_scored')} "
        f"recall_at_k={aggregate.get('recall_at_k', 0):.3f} "
        f"stale_as_fresh={aggregate.get('stale_as_fresh_count', 0)} "
        f"latency_p95_ms={aggregate.get('latency_ms_p95', 0):.3f}"
    )
