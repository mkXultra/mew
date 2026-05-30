from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import statistics
import time
from typing import Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

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
AGENT_SAVE_SOURCES = ("model", "gold")
ANSWER_SCORE_MODES = ("token_f1", "normalized_contains")

AgentActionProvider = Callable[[Mapping[str, Any]], Mapping[str, Any]]
MemoryCompressorProvider = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class ArenaRow:
    row_id: str
    task_family: str
    background: str
    backgrounds: Tuple[str, ...]
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
    background_value = _first_present(
        raw,
        (
            "background",
            "backgrounds",
            "context",
            "scenario",
            "profile",
            "memory",
            "shared_context",
            "base_person",
        ),
    )
    backgrounds = _string_sequence(background_value)
    background = backgrounds[0] if backgrounds else ""
    row_id = _clean_id(str(_first_present(raw, ("id", "task_id", "uid", "uuid")) or fallback_id))
    task_family = str(_first_present(raw, ("task_family", "category", "config", "domain")) or "memoryarena")
    return ArenaRow(
        row_id=row_id,
        task_family=task_family,
        background=background,
        backgrounds=backgrounds,
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
        nested = value.get("items") or value.get("turns") or value.get("questions") or value.get("data")
        if nested is None:
            return (_text_from_value(value),)
        value = nested
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
        metrics.update(arena_rank_metrics(result_data, expected_entry_ids=expected_ids))
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
    parts = [arena_background(row, subtask_index), arena_step_text(row.questions[subtask_index])]
    return "\n".join(part for part in parts if part)


def arena_background(row: ArenaRow, subtask_index: int) -> str:
    if row.backgrounds:
        if subtask_index < len(row.backgrounds):
            return row.backgrounds[subtask_index]
        return row.backgrounds[0]
    return row.background


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


@dataclass
class MemoryArenaNativeToolHarness:
    row: ArenaRow
    mode: str
    limit: int = 5
    include_stale: bool = False

    def __post_init__(self) -> None:
        self.entries: List[MemoryEntry] = []
        self.tool_calls: List[Dict[str, Any]] = []

    def memory_recall(self, *, query: str, subtask_index: int) -> Dict[str, Any]:
        system = MemorySystem(
            InMemoryMemoryStore(
                tuple(self.entries),
                store_id=f"memoryarena-tool:{self.row.task_family}:{self.row.row_id}:{self.mode}:{subtask_index}",
                index_id=f"memoryarena-tool:index:{self.row.row_id}:{self.mode}:{subtask_index}",
            )
        )
        request = MemoryRecallRequest(
            query=query,
            scope=f"memoryarena:{self.row.task_family}:{self.row.row_id}",
            memory_kinds=("episodic_task",),
            limit=self.limit,
            include_stale=self.include_stale,
            budget=MemoryRecallBudget(max_results=self.limit),
        )
        result = system.recall(request).to_dict()
        self.tool_calls.append(
            {
                "tool": "memory_recall",
                "subtask_index": subtask_index,
                "query_hash": stable_payload_hash({"query": query}),
                "returned_entry_ids": [item.get("entry_id") for item in result.get("candidates") or []],
                "trace_ref": result.get("trace_ref", ""),
                "dropped": dict(result.get("dropped") or {}),
            }
        )
        return result

    def memory_inspect(self, *, entry_id: str, subtask_index: int) -> Dict[str, Any]:
        wanted = str(entry_id or "").strip()
        entry = next((item for item in self.entries if item.entry_id == wanted), None)
        if entry is None or not entry.is_recallable():
            result = {"entry": None, "dropped": {"not_found": 1 if entry is None else 0}}
        else:
            result = {"entry": entry.to_dict(), "dropped": {}}
        self.tool_calls.append(
            {
                "tool": "memory_inspect",
                "subtask_index": subtask_index,
                "entry_id": wanted,
                "status": "found" if result.get("entry") else "not_found",
            }
        )
        return result

    def memory_save(
        self,
        *,
        subtask_index: int,
        content: str,
        card: Optional[Mapping[str, Any]] = None,
    ) -> Optional[str]:
        if self.mode == "memory_off":
            self.tool_calls.append(
                {
                    "tool": "memory_save",
                    "subtask_index": subtask_index,
                    "status": "skipped_memory_off",
                }
            )
            return None
        stale = self.mode == "stale"
        entry = arena_memory_tool_entry(
            self.row,
            subtask_index=subtask_index,
            content=content,
            card=card,
            stale=stale,
        )
        self.entries.append(entry)
        self.tool_calls.append(
            {
                "tool": "memory_save",
                "subtask_index": subtask_index,
                "status": "saved",
                "entry_id": entry.entry_id,
                "staleness": entry.staleness.state,
                "content_hash": stable_payload_hash({"content": content}),
                "memory_card_hash": stable_payload_hash(dict(card or {})),
            }
        )
        return entry.entry_id


def arena_memory_tool_entry(
    row: ArenaRow,
    *,
    subtask_index: int,
    content: str,
    card: Optional[Mapping[str, Any]] = None,
    stale: bool,
) -> MemoryEntry:
    question = row.questions[subtask_index] if subtask_index < len(row.questions) else ""
    entry_id = f"arena-tool:{row.row_id}:session:{subtask_index}"
    card_data = normalize_memory_arena_card(card, fallback_summary=content)
    cues = tuple(str(item).strip() for item in card_data.get("cues", ()) if str(item).strip())
    applicability = str(card_data.get("applicability") or f"Use for later MemoryArena subtasks in row {row.row_id}.")
    if cues:
        applicability = f"{applicability} Cues: {', '.join(cues[:8])}."
    payload = {
        "row_id": row.row_id,
        "question": question,
        "content": content,
        "memory_card": card_data,
        "index": subtask_index,
    }
    source_ref = ProvenanceRef(
        ref_id=f"{entry_id}:source",
        ref_kind="memoryarena_tool_save",
        artifact_path_or_uri=f"memoryarena://{row.row_id}/{subtask_index}/tool-save",
        content_hash=f"sha256:{stable_payload_hash(payload)}",
        producer="memory_arena_native_tool_harness",
    )
    proof_ref = ProvenanceRef(
        ref_id=f"{entry_id}:proof",
        ref_kind="memoryarena_gold_answer_simulated_agent_output",
        artifact_path_or_uri=f"memoryarena://{row.row_id}/{subtask_index}/answer",
        content_hash=f"sha256:{stable_payload_hash({'content': content})}",
        producer="memory_arena_native_tool_harness",
    )
    staleness = (
        Staleness(state="stale", reasons=("memory_arena_stale_mode",), invalidators=(source_ref,))
        if stale
        else Staleness()
    )
    return MemoryEntry(
        entry_id=entry_id,
        memory_kind="episodic_task",
        scope=f"memoryarena:{row.task_family}:{row.row_id}",
        title=str(card_data.get("title") or f"MemoryArena native tool save {subtask_index}"),
        summary=str(card_data.get("summary") or content),
        applicability=applicability,
        source_refs=(source_ref,),
        proof_refs=(proof_ref,),
        created_at="2026-05-20T00:00:00Z",
        last_verified_at="2026-05-20T00:00:00Z",
        validity="valid",
        confidence=float(card_data.get("confidence") or 1.0),
        staleness=staleness,
    )


def normalize_memory_arena_card(
    card: Optional[Mapping[str, Any]],
    *,
    fallback_summary: str,
) -> Dict[str, Any]:
    raw = dict(card or {})
    cues_value = raw.get("cues") or raw.get("cue") or ()
    if isinstance(cues_value, str):
        cues = (cues_value,)
    elif isinstance(cues_value, Iterable):
        cues = tuple(str(item).strip() for item in cues_value if str(item).strip())
    else:
        cues = ()
    confidence = raw.get("confidence", 1.0)
    try:
        confidence_float = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence_float = 1.0
    summary = _text_from_value(raw.get("summary") or raw.get("memory") or raw.get("content") or fallback_summary)
    title = _text_from_value(raw.get("title") or "MemoryArena compressed memory")
    applicability = _text_from_value(raw.get("applicability") or raw.get("when_to_use") or "")
    return {
        "schema": "memory_arena_card_v0",
        "title": title,
        "summary": summary,
        "cues": list(cues),
        "applicability": applicability,
        "confidence": confidence_float,
    }


def score_memory_arena_tool_artifact(
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
    tool_calls: List[Dict[str, Any]] = []
    for row in rows:
        result = score_memory_arena_tool_row(
            row,
            mode=mode,
            limit=limit,
            include_stale=include_stale,
        )
        row_results.extend(result["row_results"])
        tool_calls.extend(result["tool_calls"])
    artifact = {
        "operation": "memory_arena_tool_score",
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
            "native_memory_tool_harness": True,
            "direct_memory_system": True,
            "implement_v2_used": False,
            "model_used": False,
            "production_prompt_injection": False,
            "gold_answer_simulated_agent_output": True,
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
                "tool_harness": "memory_save_recall_v0",
            }
        ),
        "aggregate": aggregate_arena_results(row_results),
        "tool_call_counts": aggregate_tool_calls(tool_calls),
        "tool_calls": tool_calls,
        "row_results": row_results,
        "timing_ms": (time.perf_counter() - started) * 1000.0,
    }
    artifact["summary"] = format_memory_arena_summary(artifact)
    return artifact


def score_memory_arena_tool_row(
    row: ArenaRow,
    *,
    mode: str,
    limit: int,
    include_stale: bool,
) -> Dict[str, Any]:
    harness = MemoryArenaNativeToolHarness(row=row, mode=mode, limit=limit, include_stale=include_stale)
    row_results: List[Dict[str, Any]] = []
    for subtask_index, question in enumerate(row.questions):
        if subtask_index > 0:
            query = arena_query(row, subtask_index)
            expected_ids = tuple(entry.entry_id for entry in harness.entries if entry.staleness.state == "fresh")
            result_data = harness.memory_recall(query=query, subtask_index=subtask_index)
            metrics = memory_result_metrics(result_data, expected_entry_ids=expected_ids)
            metrics.update(arena_rank_metrics(result_data, expected_entry_ids=expected_ids))
            row_results.append(
                {
                    "task_family": row.task_family,
                    "task_id": row.row_id,
                    "subtask_index": subtask_index,
                    "memory_mode": mode,
                    "query": query,
                    "expected_entry_ids": list(expected_ids),
                    "memory_snapshot_hash": memory_snapshot_hash(tuple(harness.entries)),
                    "recall_config_hash": recall_config_hash(
                        {
                            "query": query,
                            "scope": f"memoryarena:{row.task_family}:{row.row_id}",
                            "limit": limit,
                            "include_stale": include_stale,
                            "tool_harness": "memory_save_recall_v0",
                        }
                    ),
                    "metrics": metrics,
                    "debug_trace": recall_debug_trace(result_data, metrics),
                    "result": result_data,
                }
            )
        if subtask_index < len(row.answers):
            content = arena_tool_memory_content(row, subtask_index)
            harness.memory_save(subtask_index=subtask_index, content=content)
    return {"row_results": tuple(row_results), "tool_calls": tuple(harness.tool_calls)}


def score_memory_arena_agent_artifact(
    *,
    input_path: Optional[str] = None,
    hf_config: Optional[str] = None,
    hf_split: str = "test",
    hf_revision: Optional[str] = None,
    mode: str,
    limit_rows: int = 0,
    limit: int = 5,
    include_stale: bool = False,
    max_turns: int = 3,
    save_source: str = "model",
    answer_score_mode: str = "token_f1",
    answer_threshold: float = 0.5,
    model_backend: str = "codex",
    model_auth: Optional[Mapping[str, Any]] = None,
    model: str = "gpt-5.5",
    base_url: str = "",
    timeout: int = 120,
    agent_provider: Optional[AgentActionProvider] = None,
    compressor_provider: Optional[MemoryCompressorProvider] = None,
) -> Dict[str, Any]:
    if mode not in MEMORY_MODES:
        raise ValueError(f"memory mode must be one of: {', '.join(MEMORY_MODES)}")
    if save_source not in AGENT_SAVE_SOURCES:
        raise ValueError(f"save_source must be one of: {', '.join(AGENT_SAVE_SOURCES)}")
    if answer_score_mode not in ANSWER_SCORE_MODES:
        raise ValueError(f"answer_score_mode must be one of: {', '.join(ANSWER_SCORE_MODES)}")
    if (agent_provider is None or compressor_provider is None) and model_auth is None:
        raise ValueError("memory-arena-agent-score requires model auth unless providers are injected")

    rows = load_memory_arena_rows(
        input_path=input_path,
        hf_config=hf_config,
        hf_split=hf_split,
        hf_revision=hf_revision,
        limit_rows=limit_rows,
    )
    started = time.perf_counter()
    row_results: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    compressor_calls: List[Dict[str, Any]] = []
    agent_calls: List[Dict[str, Any]] = []
    for row in rows:
        result = score_memory_arena_agent_row(
            row,
            mode=mode,
            limit=limit,
            include_stale=include_stale,
            max_turns=max_turns,
            save_source=save_source,
            answer_score_mode=answer_score_mode,
            answer_threshold=answer_threshold,
            model_backend=model_backend,
            model_auth=model_auth,
            model=model,
            base_url=base_url,
            timeout=timeout,
            agent_provider=agent_provider,
            compressor_provider=compressor_provider,
        )
        row_results.extend(result["row_results"])
        tool_calls.extend(result["tool_calls"])
        compressor_calls.extend(result["compressor_calls"])
        agent_calls.extend(result["agent_calls"])
    aggregate = aggregate_agent_arena_results(row_results)
    artifact = {
        "operation": "memory_arena_agent_score",
        "dataset": MEMORY_ARENA_DATASET if hf_config else "",
        "input_path": input_path or "",
        "hf_config": hf_config or "",
        "hf_split": hf_split,
        "hf_revision": hf_revision or "",
        "memory_mode": mode,
        "save_source": save_source,
        "answer_score_mode": answer_score_mode,
        "answer_threshold": answer_threshold,
        "limit_rows": limit_rows,
        "rows_loaded": len(rows),
        "queries_scored": len(row_results),
        "runner_boundary": {
            "memory_arena_style": True,
            "agent_loop_used": True,
            "native_memory_tool_harness": True,
            "direct_memory_system": True,
            "implement_v2_used": False,
            "model_used": agent_provider is None or compressor_provider is None,
            "production_prompt_injection": False,
            "short_term_session_context_hidden": True,
            "embedding_required": False,
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
                "max_turns": max_turns,
                "save_source": save_source,
                "answer_score_mode": answer_score_mode,
                "answer_threshold": answer_threshold,
                "tool_harness": "agentic_recall_inspect_v0",
            }
        ),
        "aggregate": aggregate,
        "tool_call_counts": aggregate_tool_calls(tool_calls),
        "compressor_call_count": len(compressor_calls),
        "agent_call_count": len(agent_calls),
        "tool_calls": tool_calls,
        "compressor_calls": compressor_calls,
        "agent_calls": agent_calls,
        "row_results": row_results,
        "timing_ms": (time.perf_counter() - started) * 1000.0,
    }
    artifact["summary"] = format_memory_arena_summary(artifact)
    return artifact


def score_memory_arena_agent_row(
    row: ArenaRow,
    *,
    mode: str,
    limit: int,
    include_stale: bool,
    max_turns: int,
    save_source: str,
    answer_score_mode: str,
    answer_threshold: float,
    model_backend: str,
    model_auth: Optional[Mapping[str, Any]],
    model: str,
    base_url: str,
    timeout: int,
    agent_provider: Optional[AgentActionProvider],
    compressor_provider: Optional[MemoryCompressorProvider],
) -> Dict[str, Tuple[Dict[str, Any], ...]]:
    harness = MemoryArenaNativeToolHarness(row=row, mode=mode, limit=limit, include_stale=include_stale)
    row_results: List[Dict[str, Any]] = []
    compressor_calls: List[Dict[str, Any]] = []
    agent_calls: List[Dict[str, Any]] = []
    for subtask_index, question in enumerate(row.questions):
        agent_result = run_memory_arena_agent_subtask(
            row,
            subtask_index=subtask_index,
            harness=harness,
            max_turns=max_turns,
            model_backend=model_backend,
            model_auth=model_auth,
            model=model,
            base_url=base_url,
            timeout=timeout,
            agent_provider=agent_provider,
        )
        agent_calls.extend(agent_result["agent_calls"])
        expected = row.answers[subtask_index] if subtask_index < len(row.answers) else ""
        answer_metrics = arena_answer_metrics(
            str(agent_result.get("answer") or ""),
            expected,
            mode=answer_score_mode,
            threshold=answer_threshold,
        )
        row_results.append(
            {
                "task_family": row.task_family,
                "task_id": row.row_id,
                "subtask_index": subtask_index,
                "memory_mode": mode,
                "question": arena_step_text(question),
                "expected_answer": expected,
                "answer": agent_result.get("answer") or "",
                "answer_metrics": answer_metrics,
                "agent_turns": agent_result["turns"],
                "memory_snapshot_hash_before_save": memory_snapshot_hash(tuple(harness.entries)),
            }
        )
        if subtask_index < len(row.answers):
            content = expected if save_source == "gold" else str(agent_result.get("answer") or "")
            compressor_request = {
                "row_id": row.row_id,
                "task_family": row.task_family,
                "subtask_index": subtask_index,
                "question": arena_step_text(question),
                "answer": content,
                "background": arena_background(row, subtask_index),
                "save_source": save_source,
            }
            card = compress_memory_arena_session(
                compressor_request,
                model_backend=model_backend,
                model_auth=model_auth,
                model=model,
                base_url=base_url,
                timeout=timeout,
                compressor_provider=compressor_provider,
            )
            compressor_calls.append(
                {
                    "subtask_index": subtask_index,
                    "save_source": save_source,
                    "memory_card_hash": stable_payload_hash(card),
                }
            )
            harness.memory_save(subtask_index=subtask_index, content=content, card=card)
    return {
        "row_results": tuple(row_results),
        "tool_calls": tuple(harness.tool_calls),
        "compressor_calls": tuple(compressor_calls),
        "agent_calls": tuple(agent_calls),
    }


def run_memory_arena_agent_subtask(
    row: ArenaRow,
    *,
    subtask_index: int,
    harness: MemoryArenaNativeToolHarness,
    max_turns: int,
    model_backend: str,
    model_auth: Optional[Mapping[str, Any]],
    model: str,
    base_url: str,
    timeout: int,
    agent_provider: Optional[AgentActionProvider],
) -> Dict[str, Any]:
    observations: List[Dict[str, Any]] = []
    turns: List[Dict[str, Any]] = []
    agent_calls: List[Dict[str, Any]] = []
    question = arena_step_text(row.questions[subtask_index])
    background = arena_background(row, subtask_index)
    for turn_index in range(max(1, max_turns)):
        request = {
            "row_id": row.row_id,
            "task_family": row.task_family,
            "subtask_index": subtask_index,
            "question": question,
            "background": background,
            "observations": observations,
            "available_tools": ("memory_recall", "memory_inspect"),
            "short_term_session_context_hidden": True,
        }
        action = memory_arena_agent_action(
            request,
            model_backend=model_backend,
            model_auth=model_auth,
            model=model,
            base_url=base_url,
            timeout=timeout,
            agent_provider=agent_provider,
        )
        action_name = str(action.get("action") or "").strip().casefold()
        agent_calls.append(
            {
                "subtask_index": subtask_index,
                "turn_index": turn_index,
                "action": action_name,
                "action_hash": stable_payload_hash(action),
            }
        )
        turns.append({"turn_index": turn_index, "action": action_name, "payload": redact_agent_action(action)})
        if action_name == "recall_memory":
            query = str(action.get("query") or question)
            result = harness.memory_recall(query=query, subtask_index=subtask_index)
            observations.append({"tool": "memory_recall", "result": project_recall_for_agent(result)})
            continue
        if action_name == "inspect_memory":
            result = harness.memory_inspect(
                entry_id=str(action.get("entry_id") or ""),
                subtask_index=subtask_index,
            )
            observations.append({"tool": "memory_inspect", "result": project_inspect_for_agent(result)})
            continue
        if action_name == "answer":
            return {
                "answer": _text_from_value(action.get("answer") or action.get("final_answer") or ""),
                "turns": tuple(turns),
                "agent_calls": tuple(agent_calls),
            }
        observations.append(
            {
                "tool": "agent_protocol_error",
                "result": {"message": "return recall_memory, inspect_memory, or answer"},
            }
        )
    return {"answer": "", "turns": tuple(turns), "agent_calls": tuple(agent_calls)}


def memory_arena_agent_action(
    request: Mapping[str, Any],
    *,
    model_backend: str,
    model_auth: Optional[Mapping[str, Any]],
    model: str,
    base_url: str,
    timeout: int,
    agent_provider: Optional[AgentActionProvider],
) -> Mapping[str, Any]:
    if agent_provider is not None:
        return dict(agent_provider(request))
    if model_auth is None:
        raise ValueError("agent model auth is required")
    from .model_backends import call_model_json

    prompt = memory_arena_agent_prompt(request)
    payload = call_model_json(model_backend, model_auth, prompt, model, base_url, timeout)
    if not isinstance(payload, Mapping):
        raise ValueError("memory arena agent model must return a JSON object")
    return payload


def compress_memory_arena_session(
    request: Mapping[str, Any],
    *,
    model_backend: str,
    model_auth: Optional[Mapping[str, Any]],
    model: str,
    base_url: str,
    timeout: int,
    compressor_provider: Optional[MemoryCompressorProvider],
) -> Dict[str, Any]:
    if compressor_provider is not None:
        return normalize_memory_arena_card(compressor_provider(request), fallback_summary=str(request.get("answer") or ""))
    if model_auth is None:
        raise ValueError("compressor model auth is required")
    from .model_backends import call_model_json

    prompt = memory_arena_compressor_prompt(request)
    payload = call_model_json(model_backend, model_auth, prompt, model, base_url, timeout)
    if not isinstance(payload, Mapping):
        raise ValueError("memory arena compressor model must return a JSON object")
    return normalize_memory_arena_card(payload, fallback_summary=str(request.get("answer") or ""))


def memory_arena_agent_prompt(request: Mapping[str, Any]) -> str:
    payload = {
        "task": "Answer the current MemoryArena question. Prior sessions are intentionally hidden; use memory tools if needed.",
        "protocol": {
            "recall": {"action": "recall_memory", "query": "short search cue"},
            "inspect": {"action": "inspect_memory", "entry_id": "returned memory entry id"},
            "answer": {"action": "answer", "answer": "final answer"},
        },
        "rules": [
            "Return exactly one JSON object.",
            "Do not assume previous session details unless they appear in tool observations.",
            "Use recall_memory when the question depends on earlier sessions.",
        ],
        "current_session": {
            "question": request.get("question", ""),
            "background": request.get("background", ""),
            "observations": request.get("observations", ()),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def memory_arena_compressor_prompt(request: Mapping[str, Any]) -> str:
    payload = {
        "task": "Compress this completed session into one minimal durable memory card for future recall.",
        "schema": {
            "title": "short label",
            "summary": "one or two sentences preserving only reusable facts from this session",
            "cues": ["short recall cue", "entity or task cue"],
            "applicability": "when future sessions should use this memory",
            "confidence": 0.0,
        },
        "rules": [
            "Return exactly one JSON object matching the schema.",
            "Do not include irrelevant wording or hidden future answers.",
            "Prefer compact facts over raw transcript.",
        ],
        "session": {
            "question": request.get("question", ""),
            "answer": request.get("answer", ""),
            "background": request.get("background", ""),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def project_recall_for_agent(result: Mapping[str, Any]) -> Dict[str, Any]:
    candidates = []
    for item in result.get("candidates") or []:
        if not isinstance(item, Mapping):
            continue
        candidates.append(
            {
                "entry_id": item.get("entry_id", ""),
                "kind": item.get("memory_kind", ""),
                "title": item.get("title", ""),
                "summary": item.get("summary", ""),
                "why_relevant": item.get("why_relevant", ""),
                "staleness": item.get("staleness", {}),
                "score": item.get("score", 0.0),
            }
        )
    return {"candidates": candidates, "dropped": dict(result.get("dropped") or {})}


def project_inspect_for_agent(result: Mapping[str, Any]) -> Dict[str, Any]:
    entry = result.get("entry")
    if not isinstance(entry, Mapping):
        return {"entry": None, "dropped": dict(result.get("dropped") or {})}
    return {
        "entry": {
            "entry_id": entry.get("entry_id", ""),
            "kind": entry.get("memory_kind", ""),
            "title": entry.get("title", ""),
            "summary": entry.get("summary", ""),
            "applicability": entry.get("applicability", ""),
            "staleness": entry.get("staleness", {}),
        },
        "dropped": dict(result.get("dropped") or {}),
    }


def redact_agent_action(action: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in action.items()
        if key in {"action", "query", "entry_id", "answer", "final_answer"}
    }


def arena_answer_metrics(answer: str, expected: str, *, mode: str, threshold: float) -> Dict[str, Any]:
    score = arena_answer_similarity(answer, expected, mode=mode)
    return {
        "score": score,
        "passed": score >= threshold,
        "threshold": threshold,
        "mode": mode,
        "embedding_used": False,
    }


def arena_answer_similarity(answer: str, expected: str, *, mode: str) -> float:
    answer_norm = normalize_answer_text(answer)
    expected_norm = normalize_answer_text(expected)
    if not expected_norm:
        return 1.0 if not answer_norm else 0.0
    if mode == "normalized_contains":
        if answer_norm == expected_norm or expected_norm in answer_norm:
            return 1.0
        return 0.0
    answer_terms = set(_arena_tokenize(answer_norm))
    expected_terms = set(_arena_tokenize(expected_norm))
    if not answer_terms or not expected_terms:
        return 0.0
    overlap = len(answer_terms & expected_terms)
    precision = overlap / len(answer_terms)
    recall = overlap / len(expected_terms)
    if precision + recall <= 0:
        return 0.0
    return round((2 * precision * recall) / (precision + recall), 6)


def normalize_answer_text(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _arena_tokenize(value: str) -> Tuple[str, ...]:
    cleaned = []
    for char in str(value or "").casefold():
        cleaned.append(char if char.isalnum() or char in {"_", "-", "/"} else " ")
    return tuple(token for token in "".join(cleaned).split() if token)


def aggregate_agent_arena_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = 0
    scores: List[float] = []
    turns: List[int] = []
    for row in results:
        metrics = row.get("answer_metrics") if isinstance(row.get("answer_metrics"), Mapping) else {}
        score = float(metrics.get("score") or 0.0)
        scores.append(score)
        if metrics.get("passed"):
            passed += 1
        turns.append(len(row.get("agent_turns") or ()))
    return {
        "answer_rows": total,
        "answer_pass_rows": passed,
        "answer_pass_rate": (passed / total) if total else 0.0,
        "answer_score_mean": statistics.fmean(scores) if scores else 0.0,
        "agent_turns_mean": statistics.fmean(turns) if turns else 0.0,
    }


def arena_tool_memory_content(row: ArenaRow, subtask_index: int) -> str:
    question = row.questions[subtask_index] if subtask_index < len(row.questions) else ""
    answer = row.answers[subtask_index] if subtask_index < len(row.answers) else ""
    parts = [
        f"Question: {arena_step_text(question)}",
        f"Answer: {answer}",
    ]
    background = arena_background(row, subtask_index)
    if background:
        parts.append(f"Background: {background}")
    return "\n".join(parts)


def aggregate_tool_calls(tool_calls: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for call in tool_calls:
        tool = str(call.get("tool") or "unknown")
        counts[tool] = counts.get(tool, 0) + 1
        status = str(call.get("status") or "")
        if status:
            counts[f"{tool}:{status}"] = counts.get(f"{tool}:{status}", 0) + 1
    return counts


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
    mrr_values = []
    hit_at_1 = 0
    hit_at_3 = 0
    hit_at_5 = 0
    for item in row_results:
        metrics = item.get("metrics") or {}
        stale_as_fresh += int(metrics.get("stale_recall_count") or 0)
        latencies.append(float(metrics.get("latency_ms") or 0.0))
        returned_chars.append(int(metrics.get("returned_chars") or 0))
        mrr_values.append(float(metrics.get("mrr") or 0.0))
        hit_at_1 += 1 if metrics.get("hit_at_1") else 0
        hit_at_3 += 1 if metrics.get("hit_at_3") else 0
        hit_at_5 += 1 if metrics.get("hit_at_5") else 0
    denominator = len(expected_rows) if expected_rows else 0
    return {
        "expected_rows": len(expected_rows),
        "evidence_hit_rows": len(hit_rows),
        "recall_at_k": (len(hit_rows) / len(expected_rows)) if expected_rows else 0.0,
        "hit_at_1": (hit_at_1 / denominator) if denominator else 0.0,
        "hit_at_3": (hit_at_3 / denominator) if denominator else 0.0,
        "hit_at_5": (hit_at_5 / denominator) if denominator else 0.0,
        "mrr": (sum(mrr_values) / denominator) if denominator else 0.0,
        "stale_as_fresh_count": stale_as_fresh,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
        "returned_chars_p95": _percentile(returned_chars, 95),
        "queries_scored": len(row_results),
    }


def arena_rank_metrics(
    result: Mapping[str, Any],
    *,
    expected_entry_ids: Sequence[str],
) -> Dict[str, Any]:
    candidates = list(result.get("candidates") or [])
    candidate_ids = [str(item.get("entry_id") or "") for item in candidates]
    expected = {str(entry_id) for entry_id in expected_entry_ids}
    first_rank = 0
    for index, entry_id in enumerate(candidate_ids, start=1):
        if entry_id in expected:
            first_rank = index
            break
    return {
        "first_hit_rank": first_rank,
        "hit_at_1": bool(first_rank and first_rank <= 1),
        "hit_at_3": bool(first_rank and first_rank <= 3),
        "hit_at_5": bool(first_rank and first_rank <= 5),
        "mrr": (1.0 / first_rank) if first_rank else 0.0,
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
