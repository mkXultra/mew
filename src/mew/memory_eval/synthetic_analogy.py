"""Synthetic analogy smoke loop, metrics, pack, and local profiles for memory_eval.

This module follows the reduced MVP scope described in:

- docs/IMPLEMENTATION_PLAN_2026-05-28_M6_25_SYNTHETIC_ANALOGY_MINIMAL_BENCH.md
- docs/DESIGN_2026-05-27_M6_25_SYNTHETIC_ANALOGY_MINIMAL_BENCH.md

The profile command surface is intentionally module-local and manual by default.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .adapter_contract import MemoryEvalAdapter
from .adapters.dummy import DummyPassAdapter
from .artifacts import make_failure, write_artifact
from .hashing import stable_hash


BENCHMARK_ID = "synthetic_analogy_minimal.v1"
EXACT_JSON_SCORING_ID = "exact_json_single_token_v1"
PHASE0_ALLOWED_ARTIFACT_PROVIDERS = frozenset({"retrieve_packet", "harness_baseline_packet"})
PHASE0_CONDITIONS = ("memory_off", "memory_on", "oracle_context")
PHASE0_STATE_ISOLATIONS = frozenset({"reset_per_condition_world", "reset_per_task"})
MVP1_ALLOWED_FAMILIES = frozenset({"relation_lookup", "analogy_completion", "rule_application"})
MVP1_PACK_TASK_COUNT = 20
DEFAULT_MVP1_PACK_SEED = 62525
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
SYNTHETIC_ANALOGY_PROFILE_SMOKE = "synthetic-analogy-mvp-smoke"
SYNTHETIC_ANALOGY_PROFILE_PACK20 = "synthetic-analogy-mvp-pack20"
SYNTHETIC_ANALOGY_PROFILE_NAMES = (
    SYNTHETIC_ANALOGY_PROFILE_SMOKE,
    SYNTHETIC_ANALOGY_PROFILE_PACK20,
)
PHASE4_CONDITION_COMPARISON_SCHEMA = "synthetic_analogy_condition_comparison_v1"
KNOWN_LIMITATIONS = [
    "Single fixed solver stub only; no live model execution.",
    "Profile command is local/manual only; no default CI integration.",
    "Smoke score is not benchmark-quality MVP-1 memory scoring.",
    "No long-term retention; state is reset inside the local harness.",
    "No structured claim scoring; exact JSON single-token scoring only.",
    "No terminal bench, full agent behavior, behavior_eval, or network dependency.",
]
SCORER_ONLY_FIELDS = frozenset({"hidden_world", "gold_answer", "oracle_context", "family"})
_RELATION_PROMPT_RE = re.compile(r"what\s+is\s+([a-z0-9_]+)\s+related\s+to\s+by\s+([a-z0-9_]+)\??", re.IGNORECASE)
_RELATION_FACT_RE = re.compile(
    r"\b([a-z0-9_]+)\s+is\s+([a-z0-9_]+)-related\s+to\s+([a-z0-9_]+)\b",
    re.IGNORECASE,
)
_ANALOGY_PROMPT_RE = re.compile(
    r"complete\s+the\s+analogy:\s+([a-z0-9_]+)\s+is\s+to\s+\[blank\]\s+by\s+bridge\s+([a-z0-9_]+)",
    re.IGNORECASE,
)
_ANALOGY_FACT_RE = re.compile(
    r"\banalogy\s+([a-z0-9_]+)\s+maps\s+to\s+([a-z0-9_]+)\s+by\s+bridge\s+([a-z0-9_]+)\b",
    re.IGNORECASE,
)
_RULE_PROMPT_RE = re.compile(
    r"applying\s+rule\s+([a-z0-9_]+)\s+to\s+([a-z0-9_]+)\s+gives\s+which\s+token",
    re.IGNORECASE,
)
_RULE_FACT_RE = re.compile(
    r"\brule\s+([a-z0-9_]+)\s+maps\s+([a-z0-9_]+)\s+to\s+([a-z0-9_]+)\b",
    re.IGNORECASE,
)
_ASCII_LOWERCASE_SINGLE_TOKEN_RE = re.compile(r"^[a-z]+$")


@dataclass(frozen=True)
class SyntheticAnalogyViews:
    adapter_view: dict[str, Any]
    scorer_view: dict[str, Any]
    report_view: dict[str, Any]
    id_maps: dict[str, dict[str, str]]


@dataclass(frozen=True)
class SyntheticAnalogyProfileResult:
    report: dict[str, Any]
    summary: str
    output_path: str


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
                "diagnostic": bool(task.get("diagnostic", False)),
                "diagnostics": dict(task.get("diagnostics") or {}),
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
                "diagnostic": bool(task.get("diagnostic", False)),
                "diagnostics": dict(task.get("diagnostics") or {}),
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

    condition_summaries = summarize_phase0_conditions(rows)
    comparisons = compare_phase0_conditions(rows)
    enriched_condition_summaries = attach_phase1_comparisons_to_condition_summaries(
        condition_summaries,
        comparisons,
    )
    report = {
        "benchmark_id": BENCHMARK_ID,
        "phase": "P0",
        "metrics_phase": "P1_runner_metrics_hardening",
        "state_isolation": state_isolation,
        "budget_profile": dict(effective_budget),
        "solver_profile": dict(DEFAULT_SOLVER_PROFILE),
        "score_qualification": {
            "smoke_only": True,
            "benchmark_quality": False,
            "benchmark_quality_level": None,
            "reuse_allowed_for_mvp1_benchmark": False,
            "reason": "Phase 0 uses a fixed solver stub and must not be reused as MVP-1 benchmark scoring.",
        },
        "conditions": enriched_condition_summaries,
        "condition_comparison": build_phase4_condition_comparison(
            rows,
            conditions=enriched_condition_summaries,
            comparisons=comparisons,
            budget_profile=effective_budget,
        ),
        "comparisons": comparisons,
        "per_task_rows": rows,
        "known_limitations": list(KNOWN_LIMITATIONS),
    }
    if report_path is not None:
        write_artifact(report_path, report)
    return report


def generate_mvp1_pack(seed: int = DEFAULT_MVP1_PACK_SEED) -> dict[str, Any]:
    """Generate the deterministic Phase 2 MVP-1 pack at runtime."""

    rng = random.Random(int(seed))
    tokens = _sample_token_pool(rng, count=80)
    token_index = 0

    hidden_world: dict[str, Any] = {
        "seed": int(seed),
        "entities": [],
        "relations": [],
        "analogies": [],
        "rules": [],
    }
    public_experiences: list[dict[str, str]] = []
    tasks: list[dict[str, Any]] = []
    family_plan = (
        ["relation_lookup"] * 7
        + ["analogy_completion"] * 7
        + ["rule_application"] * 6
    )
    rng.shuffle(family_plan)
    family_counts = {family: 0 for family in sorted(MVP1_ALLOWED_FAMILIES)}

    def next_token() -> str:
        nonlocal token_index
        token = tokens[token_index]
        token_index += 1
        return token

    for task_number, family in enumerate(family_plan, start=1):
        family_counts[family] += 1
        task_id = f"mvp1_{task_number:02d}_{family}"
        experience_id = f"mvp1_exp_{task_number:02d}"

        if family == "relation_lookup":
            subject = next_token()
            relation = next_token()
            answer = next_token()
            hidden_world["entities"].extend([subject, answer])
            hidden_world["relations"].append(
                {"subject": subject, "relation": relation, "object": answer}
            )
            support = f"{subject} is {relation}-related to {answer}."
            prompt = f"In this local world, what is {subject} related to by {relation}?"
        elif family == "analogy_completion":
            source = next_token()
            bridge = next_token()
            answer = next_token()
            hidden_world["entities"].extend([source, answer])
            hidden_world["analogies"].append(
                {"source": source, "bridge": bridge, "target": answer}
            )
            support = f"analogy {source} maps to {answer} by bridge {bridge}."
            prompt = (
                f"In this local world, complete the analogy: {source} is to "
                f"[blank] by bridge {bridge}. Respond with one token."
            )
        elif family == "rule_application":
            rule = next_token()
            input_token = next_token()
            answer = next_token()
            hidden_world["entities"].extend([input_token, answer])
            hidden_world["rules"].append(
                {"rule_id": rule, "input": input_token, "output": answer}
            )
            support = f"rule {rule} maps {input_token} to {answer}."
            prompt = (
                f"In this local world, applying rule {rule} to {input_token} "
                "gives which token?"
            )
        else:
            raise ValueError(f"unsupported MVP-1 family: {family}")

        if not is_ascii_lowercase_single_token(answer):
            raise ValueError(f"generated invalid answer token for {task_id}: {answer!r}")
        task = {
            "task_id": task_id,
            "family": family,
            "prompt": prompt,
            "gold_answer": answer,
            "oracle_context": [support],
            "diagnostic": False,
            "diagnostics": {
                "answer_token_leakage": _task_has_answer_token_leakage(
                    prompt=prompt,
                    gold_answer=answer,
                )
            },
        }
        if task["diagnostics"]["answer_token_leakage"]:
            task["diagnostic"] = True
        public_experiences.append({"experience_id": experience_id, "text": support})
        tasks.append(task)

    fixture = {
        "world_id": f"synthetic_analogy_mvp1_pack20_seed_{int(seed)}",
        "hidden_world": hidden_world,
        "public_experiences": public_experiences,
        "tasks": tasks,
        "pack_metadata": {
            "pack_id": "synthetic_analogy_mvp1_pack20",
            "seed": int(seed),
            "task_count": MVP1_PACK_TASK_COUNT,
            "families": sorted(MVP1_ALLOWED_FAMILIES),
            "fixture_materialization": "runtime_generation_only",
        },
    }
    if len(tasks) != MVP1_PACK_TASK_COUNT:
        raise ValueError(f"MVP-1 pack must contain {MVP1_PACK_TASK_COUNT} tasks")
    return fixture


def run_mvp1_pack20(
    adapter: MemoryEvalAdapter,
    *,
    seed: int = DEFAULT_MVP1_PACK_SEED,
    artifact_provider: str = "harness_baseline_packet",
    report_path: str | Path | None = None,
    state_isolation: str = "reset_per_condition_world",
    budget_profile: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Run the existing three-condition harness over the generated pack20."""

    fixture = generate_mvp1_pack(seed)
    suspicious_task_ids = find_answer_token_leakage_tasks(fixture)
    report = run_phase0_smoke(
        fixture,
        adapter,
        artifact_provider=artifact_provider,
        state_isolation=state_isolation,
        budget_profile=budget_profile,
    )
    report["phase"] = "P2"
    report["metrics_phase"] = "P2_deterministic_generator_mvp1_pack"
    report["pack_generation"] = {
        **dict(fixture["pack_metadata"]),
        "task_signature": mvp1_task_determinism_signature(fixture),
    }
    report["score_qualification"] = {
        "smoke_only": False,
        "benchmark_quality": True,
        "benchmark_quality_level": "mvp1_minimal_fixed_solver",
        "live_model": False,
        "reason": "Phase 2 uses the fixed in-process solver on a deterministic generated MVP-1 pack.",
    }
    report["diagnostics"] = {
        "answer_token_leakage": {
            "checked_task_count": len(fixture["tasks"]),
            "suspicious_task_ids": suspicious_task_ids,
            "normal_aggregate_excludes_suspicious": True,
        },
        "memory_off_floor": {
            "accuracy": report["conditions"]["memory_off"]["accuracy"],
            "pass_rate": report["conditions"]["memory_off"]["pass_rate"],
            "hard_threshold": None,
            "status": "diagnostic_only",
        },
    }
    report["known_limitations"] = [
        "MVP-1 fixed synthetic pack only; no live model execution.",
        "memory_off floor is diagnostic only; no hard threshold yet.",
        "Profile command is local/manual only; no default CI integration.",
        "No long-term retention; state is reset inside the local harness.",
        "No structured claim scoring; exact JSON single-token scoring only.",
        "No terminal bench, full agent behavior, behavior_eval, or network dependency.",
        "No long-horizon, stale, update, scope, forget, or full-design metrics.",
    ]
    if report_path is not None:
        write_artifact(report_path, report)
    return report


def run_synthetic_analogy_profile(
    profile_name: str,
    *,
    output_path: str | Path,
    adapter: MemoryEvalAdapter | None = None,
    seed: int = DEFAULT_MVP1_PACK_SEED,
    artifact_provider: str = "harness_baseline_packet",
) -> SyntheticAnalogyProfileResult:
    """Run one local/manual Phase 3 profile and write its JSON report."""

    if profile_name not in SYNTHETIC_ANALOGY_PROFILE_NAMES:
        allowed = ", ".join(SYNTHETIC_ANALOGY_PROFILE_NAMES)
        raise ValueError(
            f"unknown synthetic analogy profile {profile_name!r}; "
            f"available profiles: {allowed}"
        )

    runner_adapter = adapter if adapter is not None else DummyPassAdapter()
    if profile_name == SYNTHETIC_ANALOGY_PROFILE_SMOKE:
        report = run_phase0_smoke(
            _phase0_relation_lookup_smoke_fixture(),
            runner_adapter,
            artifact_provider=artifact_provider,
        )
    elif profile_name == SYNTHETIC_ANALOGY_PROFILE_PACK20:
        report = run_mvp1_pack20(
            runner_adapter,
            seed=seed,
            artifact_provider=artifact_provider,
        )
    else:  # Defensive guard for type checkers if profile constants drift.
        raise AssertionError(f"unhandled synthetic analogy profile: {profile_name!r}")

    report = _with_profile_metadata(report, profile_name=profile_name)
    write_artifact(output_path, report)
    summary = format_synthetic_analogy_profile_summary(report, output_path=output_path)
    return SyntheticAnalogyProfileResult(
        report=report,
        summary=summary,
        output_path=str(output_path),
    )


def format_synthetic_analogy_profile_summary(
    report: Mapping[str, Any],
    *,
    output_path: str | Path | None = None,
) -> str:
    profile_name = str(report.get("profile") or "")
    phase = str(report.get("phase") or "")
    condition_comparison = _condition_comparison_for_summary(report)
    comparison_rows = list(condition_comparison.get("condition_rows") or [])
    task_set = condition_comparison.get("task_set") or {}
    if not isinstance(task_set, Mapping):
        task_set = {}
    budget_limits = condition_comparison.get("budget_limits") or {}
    if not isinstance(budget_limits, Mapping):
        budget_limits = {}
    comparisons = condition_comparison.get("comparisons") or {}
    if not isinstance(comparisons, Mapping):
        comparisons = {}
    known_limitations = [
        str(item).strip().rstrip(".")
        for item in list(report.get("known_limitations") or [])
        if str(item).strip()
    ]
    lines = [
        f"Synthetic analogy profile {profile_name} completed ({phase}).",
    ]
    if output_path is not None:
        lines.append(f"JSON report: {output_path}")
    lines.append("JSON artifact is the source of record.")
    lines.append(_format_score_qualification(report))
    lines.append(
        "Task set: "
        f"same_task_set={str(bool(task_set.get('same_task_set_across_conditions'))).lower()}, "
        f"task_count={int(task_set.get('task_count') or 0)}, "
        f"diagnostic_excluded={len(list(task_set.get('diagnostic_task_ids_excluded') or []))}"
    )
    lines.append("Condition comparison:")
    for row in comparison_rows:
        if isinstance(row, Mapping):
            lines.append("- " + _format_condition_comparison_row(row, budget_limits))
    lines.append(
        "Comparisons: "
        f"memory_lift={float(comparisons.get('memory_lift') or 0.0):.3f}, "
        f"oracle_gap={float(comparisons.get('oracle_gap') or 0.0):.3f}"
    )
    if known_limitations:
        lines.append("Known limitations: " + "; ".join(known_limitations) + ".")
    lines.append(
        "Manual/local only: ci_default=false, terminal_bench=false, "
        "behavior_eval=false, live_model=false."
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local synthetic analogy MVP profiles.")
    parser.add_argument("--profile", required=True, help="Synthetic analogy profile name.")
    parser.add_argument("--output", required=True, help="Path for the JSON profile report.")
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_MVP1_PACK_SEED,
        help="Seed for synthetic-analogy-mvp-pack20 runtime generation.",
    )
    parser.add_argument(
        "--artifact-provider",
        default="harness_baseline_packet",
        choices=sorted(PHASE0_ALLOWED_ARTIFACT_PROVIDERS),
        help="MVP artifact provider to use for memory_on.",
    )
    args = parser.parse_args(argv)
    try:
        result = run_synthetic_analogy_profile(
            args.profile,
            output_path=args.output,
            seed=args.seed,
            artifact_provider=args.artifact_provider,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(result.summary)
    return 0


def mvp1_task_determinism_signature(fixture: Mapping[str, Any]) -> list[dict[str, str]]:
    signature = []
    for task in list(fixture.get("tasks") or []):
        signature.append(
            {
                "task_id": str(task.get("task_id") or ""),
                "family": str(task.get("family") or ""),
                "prompt": str(task.get("prompt") or ""),
                "gold_answer": str(task.get("gold_answer") or ""),
                "oracle_support_hash": stable_hash(_normalize_oracle_context(task.get("oracle_context"))),
            }
        )
    return signature


def find_answer_token_leakage_tasks(fixture: Mapping[str, Any]) -> list[str]:
    suspicious: list[str] = []
    for task in list(fixture.get("tasks") or []):
        if _task_has_answer_token_leakage(
            prompt=str(task.get("prompt") or ""),
            gold_answer=str(task.get("gold_answer") or ""),
        ):
            suspicious.append(str(task.get("task_id") or ""))
    return suspicious


def is_ascii_lowercase_single_token(value: str) -> bool:
    return bool(_ASCII_LOWERCASE_SINGLE_TOKEN_RE.fullmatch(str(value or "")))


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
        subset = [
            row
            for row in rows
            if row.get("condition") == condition and not bool(row.get("diagnostic", False))
        ]
        task_count = len(subset)
        if task_count == 0:
            conditions[condition] = {
                "task_count": 0,
                "per_task_success": 0.0,
                "budget_pass": 0.0,
                "task_pass": 0.0,
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
            "per_task_success": _avg(subset, "per_task_success"),
            "budget_pass": _avg_bool(subset, "budget_pass"),
            "task_pass": _avg(subset, "task_pass"),
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


def attach_phase1_comparisons_to_condition_summaries(
    conditions: Mapping[str, Mapping[str, Any]],
    comparisons: Mapping[str, float],
) -> dict[str, dict[str, Any]]:
    enriched: dict[str, dict[str, Any]] = {}
    for condition, summary in conditions.items():
        enriched[condition] = {
            **dict(summary),
            "memory_lift": float(comparisons.get("memory_lift", 0.0)),
            "oracle_gap": float(comparisons.get("oracle_gap", 0.0)),
        }
    return enriched


def build_phase4_condition_comparison(
    rows: list[Mapping[str, Any]],
    *,
    conditions: Mapping[str, Mapping[str, Any]],
    comparisons: Mapping[str, float],
    budget_profile: Mapping[str, int],
) -> dict[str, Any]:
    effective_budget = _effective_budget_profile(budget_profile)
    task_ids_by_condition: dict[str, list[str]] = {}
    diagnostic_task_ids: set[str] = set()
    for condition in PHASE0_CONDITIONS:
        seen_task_ids: set[str] = set()
        task_ids: list[str] = []
        for row in rows:
            if row.get("condition") != condition:
                continue
            task_id = str(row.get("task_id") or "")
            if bool(row.get("diagnostic", False)):
                if task_id:
                    diagnostic_task_ids.add(task_id)
                continue
            if task_id and task_id not in seen_task_ids:
                task_ids.append(task_id)
                seen_task_ids.add(task_id)
        task_ids_by_condition[condition] = task_ids

    reference_task_ids = task_ids_by_condition.get(PHASE0_CONDITIONS[0], [])
    same_task_set = all(
        task_ids_by_condition.get(condition, []) == reference_task_ids
        for condition in PHASE0_CONDITIONS
    )

    condition_rows = []
    for condition in PHASE0_CONDITIONS:
        summary = conditions.get(condition) or {}
        if not isinstance(summary, Mapping):
            summary = {}
        condition_rows.append(
            {
                "condition": condition,
                "task_count": int(summary.get("task_count") or 0),
                "accuracy": float(summary.get("accuracy") or 0.0),
                "pass_rate": float(summary.get("pass_rate") or 0.0),
                "budget_usage": {
                    "budget_pass_rate": float(summary.get("budget_pass") or 0.0),
                    "budget_violation_rate": float(
                        summary.get("budget_violation_rate") or 0.0
                    ),
                    "avg_memory_calls": float(summary.get("avg_memory_calls") or 0.0),
                    "avg_total_context_tokens": float(
                        summary.get("avg_total_context_tokens") or 0.0
                    ),
                    "avg_memory_artifact_tokens": float(
                        summary.get("avg_memory_artifact_tokens") or 0.0
                    ),
                    "avg_oracle_context_tokens": float(
                        summary.get("avg_oracle_context_tokens") or 0.0
                    ),
                    "avg_evidence_items": float(summary.get("avg_evidence_items") or 0.0),
                },
            }
        )

    return {
        "schema": PHASE4_CONDITION_COMPARISON_SCHEMA,
        "purpose": "display_only_same_task_set_condition_comparison",
        "task_set": {
            "same_task_set_across_conditions": same_task_set,
            "task_count": len(reference_task_ids),
            "task_ids": list(reference_task_ids),
            "task_ids_by_condition": task_ids_by_condition,
            "diagnostic_task_ids_excluded": sorted(diagnostic_task_ids),
        },
        "budget_limits": {
            "max_memory_calls": int(effective_budget["max_memory_calls"]),
            "max_total_context_tokens": int(effective_budget["max_total_context_tokens"]),
            "max_evidence_items": int(effective_budget["max_evidence_items"]),
        },
        "condition_rows": condition_rows,
        "comparisons": {
            "memory_lift": float(comparisons.get("memory_lift", 0.0)),
            "oracle_gap": float(comparisons.get("oracle_gap", 0.0)),
        },
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
        "diagnostic": bool(scorer_task.get("diagnostic", False)),
        "diagnostics": dict(scorer_task.get("diagnostics") or {}),
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
    analogy_match = _ANALOGY_PROMPT_RE.search(prompt)
    if analogy_match:
        source = analogy_match.group(1).lower()
        bridge = analogy_match.group(2).lower()
        for fact_source, fact_target, fact_bridge in _ANALOGY_FACT_RE.findall(condition_context):
            if fact_source.lower() == source and fact_bridge.lower() == bridge:
                return json.dumps({"answer": fact_target.lower()}, separators=(",", ":"))
    rule_match = _RULE_PROMPT_RE.search(prompt)
    if rule_match:
        rule = rule_match.group(1).lower()
        input_token = rule_match.group(2).lower()
        for fact_rule, fact_input, fact_output in _RULE_FACT_RE.findall(condition_context):
            if fact_rule.lower() == rule and fact_input.lower() == input_token:
                return json.dumps({"answer": fact_output.lower()}, separators=(",", ":"))
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


def _phase0_relation_lookup_smoke_fixture() -> dict[str, Any]:
    return {
        "world_id": "world_relation_lookup_smoke",
        "hidden_world": {
            "entities": ["dax", "wug"],
            "relations": [{"subject": "dax", "relation": "nava", "object": "wug"}],
        },
        "public_experiences": [
            {
                "experience_id": "exp_relation_fact",
                "text": "dax is nava-related to wug.",
            }
        ],
        "tasks": [
            {
                "task_id": "task_relation_lookup",
                "family": "relation_lookup",
                "prompt": "In this local world, what is dax related to by nava?",
                "gold_answer": "wug",
                "oracle_context": ["dax is nava-related to wug."],
            }
        ],
    }


def _with_profile_metadata(report: Mapping[str, Any], *, profile_name: str) -> dict[str, Any]:
    enriched = dict(report)
    enriched["profile"] = profile_name
    enriched["profile_phase"] = "P3_profile_command_manual_gate"
    enriched["profile_execution"] = {
        "local_manual_default": True,
        "ci_default_integration": False,
        "terminal_bench_integration": False,
        "behavior_eval_integration": False,
        "live_model_execution": False,
    }
    enriched["profile_report_hash"] = stable_hash(
        {key: value for key, value in enriched.items() if key != "profile_report_hash"}
    )
    return enriched


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


def _task_has_answer_token_leakage(*, prompt: str, gold_answer: str) -> bool:
    normalized_gold = _normalize_answer_text(gold_answer)
    if not normalized_gold:
        return False
    prompt_tokens = set(re.findall(r"[a-z0-9]+", str(prompt).lower()))
    return normalized_gold in prompt_tokens


def _condition_comparison_for_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    condition_comparison = report.get("condition_comparison")
    if isinstance(condition_comparison, Mapping) and isinstance(
        condition_comparison.get("condition_rows"),
        list,
    ):
        return dict(condition_comparison)

    conditions = report.get("conditions") or {}
    if not isinstance(conditions, Mapping):
        conditions = {}
    comparisons = report.get("comparisons") or {}
    if not isinstance(comparisons, Mapping):
        comparisons = {}
    budget_profile = report.get("budget_profile") or DEFAULT_BUDGET_PROFILE
    if not isinstance(budget_profile, Mapping):
        budget_profile = DEFAULT_BUDGET_PROFILE
    rows = [
        row
        for row in list(report.get("per_task_rows") or [])
        if isinstance(row, Mapping)
    ]
    return build_phase4_condition_comparison(
        rows,
        conditions=conditions,
        comparisons=comparisons,
        budget_profile=budget_profile,
    )


def _format_score_qualification(report: Mapping[str, Any]) -> str:
    qualification = report.get("score_qualification") or {}
    if not isinstance(qualification, Mapping):
        qualification = {}
    if bool(qualification.get("smoke_only")):
        return (
            "Score qualification: smoke-only; benchmark_quality=false; "
            "not MVP-1 benchmark-quality."
        )
    benchmark_quality = bool(qualification.get("benchmark_quality"))
    level = str(qualification.get("benchmark_quality_level") or "none")
    live_model = str(bool(qualification.get("live_model"))).lower()
    return (
        "Score qualification: "
        f"benchmark_quality={str(benchmark_quality).lower()}, "
        f"level={level}, live_model={live_model}."
    )


def _format_condition_comparison_row(
    row: Mapping[str, Any],
    budget_limits: Mapping[str, Any],
) -> str:
    budget_usage = row.get("budget_usage") or {}
    if not isinstance(budget_usage, Mapping):
        budget_usage = {}
    max_memory_calls = int(budget_limits.get("max_memory_calls") or 0)
    max_total_context_tokens = int(budget_limits.get("max_total_context_tokens") or 0)
    max_evidence_items = int(budget_limits.get("max_evidence_items") or 0)
    return (
        f"{row.get('condition')}: "
        f"accuracy={float(row.get('accuracy') or 0.0):.3f}, "
        f"pass_rate={float(row.get('pass_rate') or 0.0):.3f}, "
        "budget="
        f"pass={float(budget_usage.get('budget_pass_rate') or 0.0):.3f}, "
        f"violation={float(budget_usage.get('budget_violation_rate') or 0.0):.3f}, "
        f"avg_calls={float(budget_usage.get('avg_memory_calls') or 0.0):.1f}/"
        f"{max_memory_calls}, "
        "avg_total_tokens="
        f"{float(budget_usage.get('avg_total_context_tokens') or 0.0):.1f}/"
        f"{max_total_context_tokens}, "
        f"avg_evidence={float(budget_usage.get('avg_evidence_items') or 0.0):.1f}/"
        f"{max_evidence_items}"
    )


def _sample_token_pool(rng: random.Random, *, count: int) -> list[str]:
    consonants = "bcdfghjklmnpqrstvwxyz"
    vowels = "aeiou"
    candidates = [
        f"{first}{vowel}{second}"
        for first in consonants
        for vowel in vowels
        for second in consonants
        if first != second
    ]
    rng.shuffle(candidates)
    tokens = [token for token in candidates if is_ascii_lowercase_single_token(token)]
    if len(tokens) < count:
        raise ValueError(f"not enough deterministic token candidates for {count} tokens")
    return tokens[:count]


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


def _avg_bool(rows: list[Mapping[str, Any]], key: str) -> float:
    return sum(1.0 for row in rows if bool(row.get(key))) / len(rows)


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
    "DEFAULT_MVP1_PACK_SEED",
    "DEFAULT_SOLVER_PROFILE",
    "EXACT_JSON_SCORING_ID",
    "MVP1_ALLOWED_FAMILIES",
    "MVP1_PACK_TASK_COUNT",
    "PHASE0_ALLOWED_ARTIFACT_PROVIDERS",
    "PHASE4_CONDITION_COMPARISON_SCHEMA",
    "SYNTHETIC_ANALOGY_PROFILE_NAMES",
    "SYNTHETIC_ANALOGY_PROFILE_PACK20",
    "SYNTHETIC_ANALOGY_PROFILE_SMOKE",
    "SyntheticAnalogyProfileResult",
    "SyntheticAnalogyLeakageError",
    "SyntheticAnalogyViews",
    "assert_no_scorer_field_leakage",
    "attach_phase1_comparisons_to_condition_summaries",
    "build_phase4_condition_comparison",
    "compare_phase0_conditions",
    "count_mvp_whitespace_tokens",
    "find_scorer_field_leakage",
    "find_answer_token_leakage_tasks",
    "format_synthetic_analogy_profile_summary",
    "generate_mvp1_pack",
    "is_ascii_lowercase_single_token",
    "main",
    "mvp1_task_determinism_signature",
    "normalize_answer",
    "phase0_artifact_hash",
    "phase0_artifact_hash_payload",
    "run_mvp1_pack20",
    "run_phase0_smoke",
    "run_synthetic_analogy_profile",
    "score_exact_json_answer",
    "split_synthetic_analogy_fixture",
    "summarize_phase0_conditions",
]


if __name__ == "__main__":
    raise SystemExit(main())
