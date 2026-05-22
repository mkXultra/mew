"""Opt-in live-LLM runner for typed-card memory-eval fixtures.

This module is intentionally separate from the default deterministic harness.
Use it from a shell when checking the live raw-text extractor path:

    uv run python -m mew.memory_eval_live_runner fixtures/memory_eval/p1/memory_on_happy_path_basic.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .memory_eval.adapters import TypedCardsMemoryEvalAdapter
from .memory_eval.fixtures import load_fixture
from .memory_eval.runner import run_fixture
from .memory_typed_cards import RawMemoryExtractorConfig


DEFAULT_OUTPUT_ROOT = Path(".codex-artifacts") / "memory-eval-live"
DEFAULT_AUTH_JSON = Path.home() / ".codex" / "auth.json"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BACKEND = "codex"
DEFAULT_TIMEOUT = 120
LIVE_FIXTURE_SUFFIX = "_typed_live_lifecycle"
GRAPH_ON_FIXTURE_SUFFIX = "_graph_on"
NORMAL_9_SUITE = "normal-9"
GRAPH_GENERATION_SUITE = "graph-generation"
SUITES = (NORMAL_9_SUITE, GRAPH_GENERATION_SUITE)
NORMAL_9_FIXTURES = (
    Path("fixtures/memory_eval/p0/dummy_happy_path.json"),
    Path("fixtures/memory_eval/p1/memory_off_no_prior_memory_basic.json"),
    Path("fixtures/memory_eval/p1/budget_limited_basic.json"),
    Path("fixtures/memory_eval/p1/scope_isolation_basic.json"),
    Path("fixtures/memory_eval/p1/memory_on_happy_path_basic.json"),
    Path("fixtures/memory_eval/p1/retrieval_ranking_basic.json"),
    Path("fixtures/memory_eval/p1/abstention_no_memory_basic.json"),
    Path("fixtures/memory_eval/p1/update_forget_basic.json"),
    Path("fixtures/memory_eval/p1/stale_conflict_supersede_basic.json"),
)
GRAPH_GENERATION_FIXTURES = (
    Path("fixtures/memory_eval/p1/graph_expansion_basic.json"),
)


def add_seed_lifecycle(
    fixture: Mapping[str, Any],
    *,
    fixture_id_suffix: str = LIVE_FIXTURE_SUFFIX,
    reason: str = "typed-card live eval setup",
) -> dict[str, Any]:
    """Insert public seed_eval lifecycle mutations after fixture ingests.

    The typed-card adapter correctly leaves raw ingests at proposal state. P1
    retrieval fixtures need committed cards, so the live runner makes that
    eval-only setup explicit through public mutate operations.
    """

    rewritten = dict(fixture)
    fixture_id = str(rewritten.get("fixture_id") or "")
    if fixture_id_suffix and fixture_id and not fixture_id.endswith(fixture_id_suffix):
        rewritten["fixture_id"] = f"{fixture_id}{fixture_id_suffix}"

    existing_mutations = [dict(item) for item in rewritten.get("mutations") or []]
    existing_op_ids = {
        str(item.get("op_id"))
        for item in existing_mutations
        if item.get("op_id")
    }
    setup_mutations: list[dict[str, Any]] = []
    operation_sequence: list[dict[str, Any]] = []

    for operation in rewritten.get("operation_sequence") or []:
        current = dict(operation)
        operation_sequence.append(current)
        if current.get("type") != "ingest":
            continue
        experience_id = str(current.get("experience_id") or "").strip()
        if not experience_id:
            continue
        setup_op_id = _next_seed_op_id(len(setup_mutations) + 1, existing_op_ids)
        existing_op_ids.add(setup_op_id)
        setup_mutations.append(
            {
                "op_id": setup_op_id,
                "mutation_type": "seed_eval",
                "target_experience_id": experience_id,
                "effective_time": rewritten.get("evaluation_time"),
                "reason": reason,
            }
        )
        operation_sequence.append(
            {
                "type": "mutate",
                "op_id": setup_op_id,
                "ingest_order": current.get("ingest_order", len(operation_sequence)),
            }
        )

    rewritten["mutations"] = [*setup_mutations, *existing_mutations]
    rewritten["operation_sequence"] = operation_sequence
    return rewritten


def enable_graph_retrieval(
    fixture: Mapping[str, Any],
    *,
    graph_max_depth: int = 1,
    graph_max_items: int = 16,
    fixture_id_suffix: str = GRAPH_ON_FIXTURE_SUFFIX,
) -> dict[str, Any]:
    """Turn on adapter-visible graph retrieval controls for every request."""

    rewritten = dict(fixture)
    fixture_id = str(rewritten.get("fixture_id") or "")
    if fixture_id_suffix and fixture_id and not fixture_id.endswith(fixture_id_suffix):
        rewritten["fixture_id"] = f"{fixture_id}{fixture_id_suffix}"
    rewritten_requests = []
    for request in rewritten.get("requests") or []:
        current = dict(request)
        filters = dict(current.get("filters") or {})
        filters["expand_graph"] = True
        filters["graph_max_depth"] = int(graph_max_depth)
        filters["graph_max_items"] = int(graph_max_items)
        current["filters"] = filters
        rewritten_requests.append(current)
    rewritten["requests"] = rewritten_requests
    return rewritten


def run_live_typed_cards_fixture(
    fixture_path: str | Path,
    *,
    auth_json: str | Path = DEFAULT_AUTH_JSON,
    model: str = DEFAULT_MODEL,
    backend: str = DEFAULT_BACKEND,
    call_interface: str = "call_model_structured_json",
    timeout: int = DEFAULT_TIMEOUT,
    seed: int = 12345,
    fixture_ordinal: int = 1,
    run_id: str | None = None,
    created_at: str | None = None,
    output: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_ROOT,
    seed_lifecycle: bool = True,
    expand_graph: bool = False,
    graph_max_depth: int = 1,
    graph_max_items: int = 16,
) -> tuple[dict[str, Any], Path]:
    fixture_path = Path(fixture_path)
    run_id = run_id or default_run_id(fixture_path)
    fixture = load_fixture(fixture_path)
    if seed_lifecycle:
        fixture = add_seed_lifecycle(fixture)
    if expand_graph:
        fixture = enable_graph_retrieval(
            fixture,
            graph_max_depth=graph_max_depth,
            graph_max_items=graph_max_items,
        )

    extractor_config = RawMemoryExtractorConfig(
        backend=backend,
        model=model,
        auth_path=str(Path(auth_json).expanduser()),
        call_interface=call_interface,
    )
    adapter = TypedCardsMemoryEvalAdapter.live_model(
        extractor_config=extractor_config,
        timeout=timeout,
    )
    artifact = run_fixture(
        fixture,
        adapter,
        seed=seed,
        fixture_ordinal=fixture_ordinal,
        adapter_config={
            "extractor": extractor_config.to_dict(),
            "seed_lifecycle": seed_lifecycle,
            "expand_graph": expand_graph,
            "graph_max_depth": graph_max_depth,
            "graph_max_items": graph_max_items,
        },
        run_id=run_id,
        created_at=created_at,
    )
    output_path = resolve_output_path(output, output_dir=output_dir, run_id=run_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact, output_path


def run_live_typed_cards_suite(
    suite: str,
    *,
    auth_json: str | Path = DEFAULT_AUTH_JSON,
    model: str = DEFAULT_MODEL,
    backend: str = DEFAULT_BACKEND,
    call_interface: str = "call_model_structured_json",
    timeout: int = DEFAULT_TIMEOUT,
    seed: int = 12345,
    run_id: str | None = None,
    created_at: str | None = None,
    output: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_ROOT,
    seed_lifecycle: bool = True,
    expand_graph: bool = False,
    graph_max_depth: int = 1,
    graph_max_items: int = 16,
    run_fixture_fn: Any = None,
) -> tuple[dict[str, Any], Path]:
    suite = _normalize_suite_name(suite)
    run_id = run_id or default_suite_run_id(suite)
    suite_dir = Path(output_dir) / _safe_path_stem(run_id)
    run_fixture_fn = run_fixture_fn or run_live_typed_cards_fixture
    fixture_summaries = []
    failed = []
    for index, fixture in enumerate(suite_fixture_paths(suite), start=1):
        fixture_run_id = f"{run_id}_{index:02d}_{fixture.stem}"
        artifact, artifact_path = run_fixture_fn(
            fixture,
            auth_json=auth_json,
            model=model,
            backend=backend,
            call_interface=call_interface,
            timeout=timeout,
            seed=seed,
            fixture_ordinal=index,
            run_id=fixture_run_id,
            created_at=created_at,
            output=None,
            output_dir=suite_dir,
            seed_lifecycle=seed_lifecycle,
            expand_graph=expand_graph,
            graph_max_depth=graph_max_depth,
            graph_max_items=graph_max_items,
        )
        summary = summarize_artifact(artifact, artifact_path)
        summary["source_fixture"] = str(fixture)
        fixture_summaries.append(summary)
        if summary["status_counts"].get("failed") or summary["failure_count"]:
            failed.append(summary)

    suite_summary = summarize_suite(
        suite=suite,
        run_id=run_id,
        output_dir=suite_dir,
        fixtures=fixture_summaries,
        failed=failed,
        model=model,
        backend=backend,
        expand_graph=expand_graph,
    )
    output_path = resolve_suite_output_path(output, output_dir=suite_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(suite_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return suite_summary, output_path


def suite_fixture_paths(suite: str) -> tuple[Path, ...]:
    suite = _normalize_suite_name(suite)
    if suite == NORMAL_9_SUITE:
        return NORMAL_9_FIXTURES
    if suite == GRAPH_GENERATION_SUITE:
        return GRAPH_GENERATION_FIXTURES
    raise ValueError(f"unsupported live memory-eval suite: {suite}")


def summarize_suite(
    *,
    suite: str,
    run_id: str,
    output_dir: str | Path,
    fixtures: Sequence[Mapping[str, Any]],
    failed: Sequence[Mapping[str, Any]],
    model: str,
    backend: str,
    expand_graph: bool = False,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for fixture in fixtures:
        for status, count in dict(fixture.get("status_counts") or {}).items():
            status_counts[str(status)] = status_counts.get(str(status), 0) + int(count)
    return {
        "suite": suite,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "backend": backend,
        "model": model,
        "expand_graph": bool(expand_graph),
        "fixture_count": len(fixtures),
        "failed_count": len(failed),
        "status_counts": status_counts,
        "failed_fixtures": [
            {
                "source_fixture": item.get("source_fixture"),
                "fixture_id": item.get("fixture_id"),
                "status_counts": dict(item.get("status_counts") or {}),
                "failure_count": item.get("failure_count"),
                "failure_types": list(item.get("failure_types") or []),
                "output": item.get("output"),
            }
            for item in failed
        ],
        "fixtures": list(fixtures),
    }


def compact_suite_summary(summary: Mapping[str, Any], output_path: str | Path) -> dict[str, Any]:
    return {
        "suite": summary.get("suite"),
        "run_id": summary.get("run_id"),
        "output": str(output_path),
        "output_dir": summary.get("output_dir"),
        "backend": summary.get("backend"),
        "model": summary.get("model"),
        "expand_graph": bool(summary.get("expand_graph")),
        "fixture_count": summary.get("fixture_count"),
        "failed_count": summary.get("failed_count"),
        "status_counts": dict(summary.get("status_counts") or {}),
        "failed_fixtures": list(summary.get("failed_fixtures") or []),
        "fixtures": [
            {
                "source_fixture": item.get("source_fixture"),
                "fixture_id": item.get("fixture_id"),
                "status_counts": dict(item.get("status_counts") or {}),
                "failure_count": item.get("failure_count"),
                "output": item.get("output"),
            }
            for item in summary.get("fixtures") or []
            if isinstance(item, Mapping)
        ],
    }


def default_run_id(fixture_path: str | Path) -> str:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    stem = _safe_path_stem(Path(fixture_path).stem)
    return f"live_typed_cards_{stem}_{timestamp}"


def default_suite_run_id(suite: str) -> str:
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    return f"live_typed_cards_{_safe_path_stem(suite)}_{timestamp}"


def resolve_output_path(
    output: str | Path | None,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_ROOT,
    run_id: str,
) -> Path:
    if output is not None:
        return Path(output)
    return Path(output_dir) / f"{_safe_path_stem(run_id)}.json"


def resolve_suite_output_path(output: str | Path | None, *, output_dir: str | Path) -> Path:
    if output is not None:
        return Path(output)
    return Path(output_dir) / "summary.json"


def summarize_artifact(artifact: Mapping[str, Any], output_path: str | Path) -> dict[str, Any]:
    requests = list(artifact.get("requests") or [])
    return {
        "run_id": artifact.get("run_id"),
        "output": str(output_path),
        "fixture_id": (artifact.get("fixture") or {}).get("fixture_id"),
        "adapter_id": (artifact.get("adapter") or {}).get("adapter_id"),
        "external_model_ids": list((artifact.get("adapter") or {}).get("external_model_ids") or []),
        "status_counts": dict((artifact.get("aggregate_metrics") or {}).get("status_counts") or {}),
        "hard_gates": list(artifact.get("hard_gates") or []),
        "failure_count": len(artifact.get("failures") or []),
        "failure_types": sorted(
            {
                str(failure.get("type"))
                for failure in artifact.get("failures") or []
                if isinstance(failure, Mapping) and failure.get("type")
            }
        ),
        "requests": [
            {
                "request_id": request.get("fixture_request_id") or request.get("request_id"),
                "status": request.get("result_status"),
                "metrics": dict(request.get("metrics") or {}),
                "failure_types": sorted(
                    {
                        str(failure.get("type"))
                        for failure in request.get("failures") or []
                        if isinstance(failure, Mapping) and failure.get("type")
                    }
                ),
            }
            for request in requests
        ],
    }


def exit_code_for_artifact(artifact: Mapping[str, Any], *, allow_failures: bool = False) -> int:
    if allow_failures:
        return 0
    status_counts = dict((artifact.get("aggregate_metrics") or {}).get("status_counts") or {})
    if status_counts.get("failed"):
        return 1
    if artifact.get("failures"):
        return 1
    return 0


def exit_code_for_suite(summary: Mapping[str, Any], *, allow_failures: bool = False) -> int:
    if allow_failures:
        return 0
    return 1 if int(summary.get("failed_count") or 0) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run typed-card memory-eval fixtures through the live raw-memory LLM extractor."
    )
    parser.add_argument("fixture", type=Path, nargs="?", help="Memory-eval fixture JSON path.")
    parser.add_argument("--suite", choices=SUITES, help="Run a built-in fixture suite instead of a single fixture.")
    parser.add_argument(
        "--all-normal",
        action="store_const",
        const=NORMAL_9_SUITE,
        dest="suite",
        help="Alias for --suite normal-9.",
    )
    parser.add_argument("--auth-json", type=Path, default=DEFAULT_AUTH_JSON)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    parser.add_argument(
        "--call-interface",
        choices=("call_model_structured_json", "call_model_json"),
        default="call_model_structured_json",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--fixture-ordinal", type=int, default=1)
    parser.add_argument("--run-id")
    parser.add_argument("--created-at")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--no-seed-lifecycle",
        action="store_false",
        dest="seed_lifecycle",
        help="Do not insert eval-only seed_eval mutations after ingests.",
    )
    parser.add_argument(
        "--expand-graph",
        action="store_true",
        help="Set adapter-visible graph expansion controls on every request.",
    )
    parser.add_argument("--graph-max-depth", type=int, default=1)
    parser.add_argument("--graph-max-items", type=int, default=16)
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Always exit 0 after writing the artifact, even if scoring failed.",
    )
    parser.add_argument("--print-artifact", action="store_true")
    parser.set_defaults(seed_lifecycle=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.suite:
        summary, output_path = run_live_typed_cards_suite(
            args.suite,
            auth_json=args.auth_json,
            model=args.model,
            backend=args.backend,
            call_interface=args.call_interface,
            timeout=args.timeout,
            seed=args.seed,
            run_id=args.run_id,
            created_at=args.created_at,
            output=args.output,
            output_dir=args.output_dir,
            seed_lifecycle=args.seed_lifecycle,
            expand_graph=args.expand_graph,
            graph_max_depth=args.graph_max_depth,
            graph_max_items=args.graph_max_items,
        )
        print(json.dumps(compact_suite_summary(summary, output_path), ensure_ascii=False, sort_keys=True))
        if args.print_artifact:
            print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return exit_code_for_suite(summary, allow_failures=args.allow_failures)

    if args.fixture is None:
        raise SystemExit("fixture is required unless --suite or --all-normal is provided")
    artifact, output_path = run_live_typed_cards_fixture(
        args.fixture,
        auth_json=args.auth_json,
        model=args.model,
        backend=args.backend,
        call_interface=args.call_interface,
        timeout=args.timeout,
        seed=args.seed,
        fixture_ordinal=args.fixture_ordinal,
        run_id=args.run_id,
        created_at=args.created_at,
        output=args.output,
        output_dir=args.output_dir,
        seed_lifecycle=args.seed_lifecycle,
        expand_graph=args.expand_graph,
        graph_max_depth=args.graph_max_depth,
        graph_max_items=args.graph_max_items,
    )
    print(json.dumps(summarize_artifact(artifact, output_path), ensure_ascii=False, sort_keys=True))
    if args.print_artifact:
        print(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
    return exit_code_for_artifact(artifact, allow_failures=args.allow_failures)


def _next_seed_op_id(index: int, existing_op_ids: set[str]) -> str:
    candidate = f"setup_seed_{index:06d}"
    while candidate in existing_op_ids:
        index += 1
        candidate = f"setup_seed_{index:06d}"
    return candidate


def _safe_path_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    return cleaned.strip("._-") or "run"


def _normalize_suite_name(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized == "normal_9":
        normalized = NORMAL_9_SUITE
    if normalized == "graph_generation":
        normalized = GRAPH_GENERATION_SUITE
    if normalized not in SUITES:
        raise ValueError(f"unsupported live memory-eval suite: {value}")
    return normalized


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
