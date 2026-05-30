"""Phase 0 synthetic analogy smoke loop for memory_eval.

This module intentionally implements only the MVP-0 plumbing described in:

- docs/IMPLEMENTATION_PLAN_2026-05-28_M6_25_SYNTHETIC_ANALOGY_MINIMAL_BENCH.md
- docs/DESIGN_2026-05-27_M6_25_SYNTHETIC_ANALOGY_MINIMAL_BENCH.md

It does not implement the Phase 1+ benchmark pack, richer metrics, or CLI
integration.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .adapter_contract import MemoryEvalAdapter
from .artifacts import make_failure, write_artifact
from .hashing import stable_hash


BENCHMARK_ID = "synthetic_analogy_minimal.v1"
EXACT_JSON_SCORING_ID = "exact_json_single_token_v1"
PHASE0_ALLOWED_ARTIFACT_PROVIDERS = frozenset({"retrieve_packet", "harness_baseline_packet"})
PHASE0_CONDITIONS = ("memory_off", "memory_on", "oracle_context")
PHASE0_STATE_ISOLATIONS = frozenset({"reset_per_condition_world", "reset_per_task"})
DEFAULT_BUDGET_PROFILE = {
    "max_memory_calls": 1,
    "max_total_context_tokens": 600,
    "max_evidence_items": 8,
}
DEFAULT_SOLVER_PROFILE = {
    "solver_id": "fixed_solver_v1",
    "answer_format": "json_single_token",
    "token_counter": "mvp_whitespace_v1",
}
KNOWN_LIMITATIONS = [
    "Phase 0 smoke-only score; not benchmark-quality memory scoring.",
    "Single fixed solver stub only; no live model execution.",
    "No Phase 1 metrics hardening, generator pack, or CLI profile wiring.",
    "No terminal bench, behavior_eval, or network dependency.",
]
SCORER_ONLY_FIELDS = frozenset({"hidden_world", "gold_answer", "oracle_context", "family"})
_RELATION_PROMPT_RE = re.compile(r"what\s+is\s+([a-z0-9_]+)\s+related\s+to\s+by\s+([a-z0-9_]+)\??", re.IGNORECASE)
_RELATION_FACT_RE = re.compile(
    r"\b([a-z0-9_]+)\s+is\s+([a-z0-9_]+)-related\s+to\s+([a-z0-9_]+)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SyntheticAnalogyViews:
    adapter_view: dict[str, Any]
    scorer_view: dict[str, Any]
    report_view: dict[str, Any]
    id_maps: dict[str, dict[str, str]]


class SyntheticAnalogyLeakageError(ValueError):
    """Raised when scorer-only fields leak into adapter/artifact-visible inputs."""

    def __init__(self, failures: list[dict[str, Any]]) -> None:
        super().__init__("synthetic analogy scorer-only data leaked into public inputs")
        self.failures = failures


def split_synthetic_analogy_fixture(
    fixture: Mapping[str, Any],
    *,
    budget_profile: Mapping[str, int] | None = None,
) -> SyntheticAnalogyViews:
    source = json.loads(json.dumps(dict(fixture)))
    world_id = str(source.get("world_id") or "world_001")
    adapter_world_id = "world_000001"
    public_experiences = list(source.get("public_experiences") or [])
    tasks = list(source.get("tasks") or [])
    effective_budget = _effective_budget_profile(budget_profile)

    experience_id_map = {
        str(item.get("experience_id") or f"exp_{index:03d}"): f"ex_{index:06d}"
        for index, item in enumerate(public_experiences, start=1)
    }
    task_id_map = {
        str(item.get("task_id") or f"task_{index:03d}"): f"rq_{index:06d}"
        for index, item in enumerate(tasks, start=1)
    }
    scope_id = f"synthetic/{adapter_world_id}"

    adapter_public_experiences = []
    for index, item in enumerate(public_experiences, start=1):
        source_experience_id = str(item.get("experience_id") or f"exp_{index:03d}")
        adapter_public_experiences.append(
            {
                "experience_id": experience_id_map[source_experience_id],
                "scope_id": scope_id,
                "ingest_order": index,
                "payload": {
                    "text": str(item.get("text") or ""),
                    "mime_type": "text/plain",
                },
                "visibility": {
                    "retrievable": True,
                    "allowed_scope_ids": [scope_id],
                },
            }
        )

    adapter_tasks = []
    scorer_tasks = []
    report_tasks = []
    for index, task in enumerate(tasks, start=1):
        source_task_id = str(task.get("task_id") or f"task_{index:03d}")
        adapter_task_id = task_id_map[source_task_id]
        prompt = str(task.get("prompt") or "")
        oracle_context = _normalize_oracle_context(task.get("oracle_context"))
        scorer_tasks.append(
            {
                "task_id": source_task_id,
                "adapter_task_id": adapter_task_id,
                "family": str(task.get("family") or ""),
                "prompt": prompt,
                "gold_answer": str(task.get("gold_answer") or ""),
                "oracle_context": oracle_context,
            }
        )
        adapter_tasks.append(
            {
                "task_id": adapter_task_id,
                "prompt": prompt,
                "scope_id": scope_id,
                "budget_profile": dict(effective_budget),
            }
        )
        report_tasks.append(
            {
                "task_id": source_task_id,
                "family": str(task.get("family") or ""),
                "prompt": prompt,
            }
        )

    adapter_view = {
        "benchmark_id": BENCHMARK_ID,
        "world_id": adapter_world_id,
        "scope_id": scope_id,
        "budget_profile": dict(effective_budget),
        "public_experiences": adapter_public_experiences,
        "tasks": adapter_tasks,
    }
    scorer_view = {
        "benchmark_id": BENCHMARK_ID,
        "world_id": world_id,
        "hidden_world": source.get("hidden_world") or {},
        "tasks": scorer_tasks,
    }
    report_view = {
        "benchmark_id": BENCHMARK_ID,
        "world_id": world_id,
        "tasks": report_tasks,
    }
    return SyntheticAnalogyViews(
        adapter_view=adapter_view,
        scorer_view=scorer_view,
        report_view=report_view,
        id_maps={
            "experience_id_to_adapter": experience_id_map,
            "adapter_experience_id_to_source": {value: key for key, value in experience_id_map.items()},
            "task_id_to_adapter": task_id_map,
            "adapter_task_id_to_source": {value: key for key, value in task_id_map.items()},
        },
    )


def run_phase0_smoke(
    fixture: Mapping[str, Any],
    adapter: MemoryEvalAdapter,
    *,
    artifact_provider: str = "harness_baseline_packet",
    report_path: str | Path | None = None,
    state_isolation: str = "reset_per_condition_world",
    budget_profile: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    if artifact_provider not in PHASE0_ALLOWED_ARTIFACT_PROVIDERS:
        allowed = ", ".join(sorted(PHASE0_ALLOWED_ARTIFACT_PROVIDERS))
        raise ValueError(f"artifact_provider must be one of: {allowed}")
    if state_isolation not in PHASE0_STATE_ISOLATIONS:
        allowed = ", ".join(sorted(PHASE0_STATE_ISOLATIONS))
        raise ValueError(f"state_isolation must be one of: {allowed}")

    effective_budget = _effective_budget_profile(budget_profile)
    views = split_synthetic_analogy_fixture(fixture, budget_profile=effective_budget)
    assert_no_scorer_field_leakage(views.adapter_view, context="adapter_view")

    rows: list[dict[str, Any]] = []
    if state_isolation == "reset_per_condition_world":
        for condition in PHASE0_CONDITIONS:
            _reset_condition_state(adapter, views, condition)
            rows.extend(
                _run_condition_rows(
                    adapter=adapter,
                    views=views,
                    condition=condition,
                    artifact_provider=artifact_provider,
                    budget_profile=effective_budget,
                )
            )
    else:
        for condition in PHASE0_CONDITIONS:
            for public_task, scorer_task in zip(views.adapter_view["tasks"], views.scorer_view["tasks"], strict=True):
                _reset_condition_state(adapter, views, condition)
                rows.append(
                    _run_single_condition_task(
                        adapter=adapter,
                        views=views,
                        condition=condition,
                        public_task=public_task,
                        scorer_task=scorer_task,
                        artifact_provider=artifact_provider,
                        budget_profile=effective_budget,
                    )
                )

    report = {
        "benchmark_id": BENCHMARK_ID,
        "phase": "P0",
        "state_isolation": state_isolation,
        "budget_profile": dict(effective_budget),
        "solver_profile": dict(DEFAULT_SOLVER_PROFILE),
        "score_qualification": {
            "smoke_only": True,
            "benchmark_quality": False,
            "reuse_allowed_for_mvp1_benchmark": False,
            "reason": "Phase 0 uses a fixed solver stub and must not be reused as MVP-1 benchmark scoring.",
        },
        "conditions": summarize_phase0_conditions(rows),
        "comparisons": compare_phase0_conditions(rows),
        "per_task_rows": rows,
        "known_limitations": list(KNOWN_LIMITATIONS),
    }
    if report_path is not None:
        write_artifact(report_path, report)
    return report


def count_mvp_whitespace_tokens(text: str) -> int:
    return len(str(text or "").split())


def normalize_answer(raw_output: str | Mapping[str, Any]) -> str:
    if isinstance(raw_output, Mapping):
        payload = dict(raw_output)
    else:
        try:
            payload = json.loads(str(raw_output))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_json") from exc
    answer = payload.get("answer")
    if not isinstance(answer, str):
        raise ValueError("missing_answer")
    normalized = _normalize_answer_text(answer)
    if not normalized:
        raise ValueError("empty_answer")
    if len(normalized.split(" ")) != 1:
        raise ValueError("multiple_tokens")
    return normalized


def score_exact_json_answer(raw_output: str | Mapping[str, Any], gold_answer: str) -> dict[str, Any]:
    normalized_gold_answer = _normalize_answer_text(gold_answer)
    result = {
        "score_method": EXACT_JSON_SCORING_ID,
        "raw_output": raw_output if isinstance(raw_output, str) else json.dumps(raw_output, sort_keys=True),
        "normalized_answer": None,
        "normalized_gold_answer": normalized_gold_answer,
        "parse_ok": False,
        "error": None,
        "is_correct": False,
    }
    try:
        normalized_answer = normalize_answer(raw_output)
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    result["normalized_answer"] = normalized_answer
    result["parse_ok"] = True
    result["is_correct"] = normalized_answer == normalized_gold_answer
    return result


def phase0_artifact_hash_payload(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": artifact.get("artifact_id"),
        "task_id": artifact.get("task_id"),
        "world_id": artifact.get("world_id"),
        "condition": artifact.get("condition"),
        "artifact_provider": artifact.get("artifact_provider"),
        "artifact_text": artifact.get("artifact_text"),
        "evidence_ids": list(artifact.get("evidence_ids") or []),
        "memory_calls_used": artifact.get("memory_calls_used"),
        "memory_artifact_tokens_used": artifact.get("memory_artifact_tokens_used"),
    }


def phase0_artifact_hash(artifact: Mapping[str, Any]) -> str:
    return stable_hash(phase0_artifact_hash_payload(artifact))


def assert_no_scorer_field_leakage(payload: Mapping[str, Any], *, context: str) -> None:
    failures = find_scorer_field_leakage(payload, context=context)
    if failures:
        raise SyntheticAnalogyLeakageError(failures)


def find_scorer_field_leakage(payload: Mapping[str, Any], *, context: str) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for path, key in _walk_keys(payload):
        if key in SCORER_ONLY_FIELDS:
            failures.append(
                make_failure(
                    stage="synthetic_analogy",
                    type="scorer_field_leakage",
                    gate_id="no_scorer_field_leakage",
                    message=f"{context} contains scorer-only field {key!r} at {path}.",
                    expected="no scorer-only fields in adapter/artifact-visible payloads",
                    actual={"context": context, "path": path, "field": key},
                )
            )
    return failures


def summarize_phase0_conditions(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    conditions: dict[str, dict[str, Any]] = {}
    for condition in PHASE0_CONDITIONS:
        subset = [row for row in rows if row.get("condition") == condition]
        task_count = len(subset)
        if task_count == 0:
            conditions[condition] = {
                "task_count": 0,
                "accuracy": 0.0,
                "pass_rate": 0.0,
                "avg_memory_calls": 0.0,
                "avg_task_prompt_tokens": 0.0,
                "avg_memory_artifact_tokens": 0.0,
                "avg_oracle_context_tokens": 0.0,
                "avg_total_context_tokens": 0.0,
                "avg_evidence_items": 0.0,
                "budget_violation_rate": 0.0,
            }
            continue

        conditions[condition] = {
            "task_count": task_count,
            "accuracy": _avg(subset, "per_task_success"),
            "pass_rate": _avg(subset, "task_pass"),
            "avg_memory_calls": _avg(subset, "memory_calls_used"),
            "avg_task_prompt_tokens": _avg(subset, "task_prompt_tokens_used"),
            "avg_memory_artifact_tokens": _avg(subset, "memory_artifact_tokens_used"),
            "avg_oracle_context_tokens": _avg(subset, "oracle_context_tokens_used"),
            "avg_total_context_tokens": _avg(subset, "total_context_tokens_used"),
            "avg_evidence_items": _avg(subset, "evidence_items_used"),
            "budget_violation_rate": _avg_bool_inverse(subset, "budget_pass"),
        }
    return conditions


def compare_phase0_conditions(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    by_condition = summarize_phase0_conditions(rows)
    return {
        "memory_lift": by_condition["memory_on"]["accuracy"] - by_condition["memory_off"]["accuracy"],
        "oracle_gap": by_condition["oracle_context"]["accuracy"] - by_condition["memory_on"]["accuracy"],
        "memory_pass_lift": by_condition["memory_on"]["pass_rate"] - by_condition["memory_off"]["pass_rate"],
        "oracle_pass_gap": by_condition["oracle_context"]["pass_rate"] - by_condition["memory_on"]["pass_rate"],
    }


def _run_condition_rows(
    *,
    adapter: MemoryEvalAdapter,
    views: SyntheticAnalogyViews,
    condition: str,
    artifact_provider: str,
    budget_profile: Mapping[str, int],
) -> list[dict[str, Any]]:
    rows = []
    for public_task, scorer_task in zip(views.adapter_view["tasks"], views.scorer_view["tasks"], strict=True):
        rows.append(
            _run_single_condition_task(
                adapter=adapter,
                views=views,
                condition=condition,
                public_task=public_task,
                scorer_task=scorer_task,
                artifact_provider=artifact_provider,
                budget_profile=budget_profile,
            )
        )
    return rows


def _run_single_condition_task(
    *,
    adapter: MemoryEvalAdapter,
    views: SyntheticAnalogyViews,
    condition: str,
    public_task: Mapping[str, Any],
    scorer_task: Mapping[str, Any],
    artifact_provider: str,
    budget_profile: Mapping[str, int],
) -> dict[str, Any]:
    prompt = str(public_task.get("prompt") or "")
    artifact: dict[str, Any] | None = None
    oracle_context_text = ""
    if condition == "memory_on":
        artifact = _build_memory_on_artifact(
            adapter=adapter,
            views=views,
            public_task=public_task,
            scorer_task=scorer_task,
            artifact_provider=artifact_provider,
            budget_profile=budget_profile,
        )
        solver_input_context = artifact["artifact_text"]
    elif condition == "oracle_context":
        oracle_context_items = _normalize_oracle_context(scorer_task.get("oracle_context"))
        oracle_context_text = "\n".join(str(item) for item in oracle_context_items)
        solver_input_context = oracle_context_text
    else:
        solver_input_context = ""

    solver_output = _fixed_solver_v1(prompt=prompt, condition_context=solver_input_context)
    scoring = score_exact_json_answer(solver_output, str(scorer_task.get("gold_answer") or ""))
    per_task_success = int(bool(scoring["is_correct"]))
    task_prompt_tokens = count_mvp_whitespace_tokens(prompt)
    memory_artifact_tokens = count_mvp_whitespace_tokens(artifact["artifact_text"]) if artifact else 0
    oracle_context_tokens = count_mvp_whitespace_tokens(oracle_context_text)
    total_context_tokens = task_prompt_tokens + memory_artifact_tokens + oracle_context_tokens
    evidence_items_used = _evidence_items_used(condition=condition, artifact=artifact, scorer_task=scorer_task)
    memory_calls_used = int(artifact["memory_calls_used"]) if artifact else 0
    budget_pass = (
        memory_calls_used <= int(budget_profile["max_memory_calls"])
        and total_context_tokens <= int(budget_profile["max_total_context_tokens"])
        and evidence_items_used <= int(budget_profile["max_evidence_items"])
    )

    return {
        "task_id": str(scorer_task.get("task_id") or ""),
        "world_id": str(views.report_view.get("world_id") or ""),
        "condition": condition,
        "family": str(scorer_task.get("family") or ""),
        "solver_output": solver_output,
        "normalized_answer": scoring["normalized_answer"],
        "per_task_success": per_task_success,
        "artifact_id": artifact["artifact_id"] if artifact else None,
        "artifact_hash": artifact["artifact_hash"] if artifact else None,
        "artifact_provider": artifact["artifact_provider"] if artifact else None,
        "artifact_text": artifact["artifact_text"] if artifact else "",
        "evidence_ids": list(artifact["evidence_ids"]) if artifact else [],
        "memory_calls_used": memory_calls_used,
        "task_prompt_tokens_used": task_prompt_tokens,
        "memory_artifact_tokens_used": memory_artifact_tokens,
        "oracle_context_tokens_used": oracle_context_tokens,
        "total_context_tokens_used": total_context_tokens,
        "evidence_items_used": evidence_items_used,
        "budget_pass": budget_pass,
        "task_pass": int(per_task_success == 1 and budget_pass),
        "scoring": scoring,
    }


def _build_memory_on_artifact(
    *,
    adapter: MemoryEvalAdapter,
    views: SyntheticAnalogyViews,
    public_task: Mapping[str, Any],
    scorer_task: Mapping[str, Any],
    artifact_provider: str,
    budget_profile: Mapping[str, int],
) -> dict[str, Any]:
    query_payload = {
        "request_id": str(public_task.get("task_id") or ""),
        "scope_id": str(public_task.get("scope_id") or ""),
        "k": int(budget_profile["max_evidence_items"]),
        "budget": {"max_evidence_items": int(budget_profile["max_evidence_items"])},
        "query": {"text": str(public_task.get("prompt") or ""), "intent": "synthetic_analogy_smoke"},
    }
    assert_no_scorer_field_leakage(query_payload, context="memory_on_query_payload")

    retrieval = dict(adapter.retrieve(query_payload))
    artifact_input = {
        "task_id": public_task.get("task_id"),
        "artifact_provider": artifact_provider,
        "query_payload": query_payload,
        "retrieval": retrieval,
        "public_experiences": views.adapter_view.get("public_experiences"),
    }
    assert_no_scorer_field_leakage(artifact_input, context="memory_on_artifact_input")

    evidence_ids: list[str] = []
    artifact_lines: list[str] = []
    public_experiences = {
        str(item.get("experience_id") or ""): item for item in views.adapter_view.get("public_experiences", [])
    }

    for item in list(retrieval.get("ranked_evidence") or []):
        adapter_evidence_id = str(item.get("evidence_id") or "")
        if not adapter_evidence_id:
            continue
        public_item = public_experiences.get(adapter_evidence_id)
        if public_item is None:
            continue
        evidence_ids.append(adapter_evidence_id)
        artifact_line = _artifact_line_for_provider(
            artifact_provider=artifact_provider,
            retrieval_item=item,
            public_item=public_item,
        )
        artifact_lines.append(artifact_line)

    artifact_text = "\n".join(line for line in artifact_lines if line)
    artifact = {
        "artifact_id": (
            f"artifact_{views.report_view.get('world_id')}_{scorer_task.get('task_id')}_{condition_name('memory_on')}"
        ),
        "task_id": str(scorer_task.get("task_id") or ""),
        "world_id": str(views.report_view.get("world_id") or ""),
        "condition": "memory_on",
        "artifact_provider": artifact_provider,
        "memory_calls_used": 1,
        "memory_artifact_tokens_used": count_mvp_whitespace_tokens(artifact_text),
        "artifact_text": artifact_text,
        "evidence_ids": evidence_ids,
    }
    artifact["artifact_hash"] = phase0_artifact_hash(artifact)
    return artifact


def _reset_condition_state(
    adapter: MemoryEvalAdapter,
    views: SyntheticAnalogyViews,
    condition: str,
) -> None:
    adapter.reset(
        {
            "benchmark_id": BENCHMARK_ID,
            "world_id": views.adapter_view.get("world_id"),
            "condition": condition,
            "scope_id": views.adapter_view.get("scope_id"),
        }
    )
    if condition == "memory_on":
        adapter.ingest(list(views.adapter_view.get("public_experiences") or []))


def _fixed_solver_v1(*, prompt: str, condition_context: str) -> str:
    prompt_match = _RELATION_PROMPT_RE.search(prompt)
    if prompt_match:
        subject = prompt_match.group(1).lower()
        relation = prompt_match.group(2).lower()
        for fact_subject, fact_relation, fact_object in _RELATION_FACT_RE.findall(condition_context):
            if fact_subject.lower() == subject and fact_relation.lower() == relation:
                return json.dumps({"answer": fact_object.lower()}, separators=(",", ":"))
    return json.dumps({"answer": "unknown"}, separators=(",", ":"))


def _artifact_line_for_provider(
    *,
    artifact_provider: str,
    retrieval_item: Mapping[str, Any],
    public_item: Mapping[str, Any],
) -> str:
    if artifact_provider == "retrieve_packet":
        for key in ("artifact_text", "text", "snippet"):
            value = retrieval_item.get(key)
            if isinstance(value, str) and value:
                return value
        metadata = retrieval_item.get("metadata") or {}
        if isinstance(metadata, Mapping):
            text_value = metadata.get("text")
            if isinstance(text_value, str) and text_value:
                return text_value

    payload = public_item.get("payload") or {}
    return str(payload.get("text") or "")


def _effective_budget_profile(budget_profile: Mapping[str, int] | None) -> dict[str, int]:
    effective = dict(DEFAULT_BUDGET_PROFILE)
    if budget_profile:
        effective.update({key: int(value) for key, value in dict(budget_profile).items()})
    return effective


def _normalize_oracle_context(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    raise ValueError(
        "oracle_context must be None, a string, or a list/tuple of strings; "
        f"got {type(value).__name__}"
    )


def _normalize_answer_text(value: str) -> str:
    stripped = re.sub(r"\s+", " ", str(value or "").strip())
    normalized_chars = [char.lower() if "A" <= char <= "Z" else char for char in stripped]
    return "".join(normalized_chars)


def _evidence_items_used(
    *,
    condition: str,
    artifact: Mapping[str, Any] | None,
    scorer_task: Mapping[str, Any],
) -> int:
    if condition == "memory_on":
        return len(list((artifact or {}).get("evidence_ids") or []))
    if condition == "oracle_context":
        return len(_normalize_oracle_context(scorer_task.get("oracle_context")))
    return 0


def _avg(rows: list[Mapping[str, Any]], key: str) -> float:
    return sum(float(row.get(key) or 0) for row in rows) / len(rows)


def _avg_bool_inverse(rows: list[Mapping[str, Any]], key: str) -> float:
    return sum(1.0 for row in rows if not bool(row.get(key))) / len(rows)


def _walk_keys(value: Any, path: str = "$"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key)
            yield from _walk_keys(child, child_path)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_keys(child, f"{path}[{index}]")


def condition_name(value: str) -> str:
    return str(value or "")


__all__ = [
    "BENCHMARK_ID",
    "DEFAULT_BUDGET_PROFILE",
    "DEFAULT_SOLVER_PROFILE",
    "EXACT_JSON_SCORING_ID",
    "PHASE0_ALLOWED_ARTIFACT_PROVIDERS",
    "SyntheticAnalogyLeakageError",
    "SyntheticAnalogyViews",
    "assert_no_scorer_field_leakage",
    "compare_phase0_conditions",
    "count_mvp_whitespace_tokens",
    "find_scorer_field_leakage",
    "normalize_answer",
    "phase0_artifact_hash",
    "phase0_artifact_hash_payload",
    "run_phase0_smoke",
    "score_exact_json_answer",
    "split_synthetic_analogy_fixture",
    "summarize_phase0_conditions",
]
