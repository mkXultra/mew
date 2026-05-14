"""Sidecar hot-path step-diff analyzer for M6.24 diagnostics.

The analyzer compares an existing reference-agent normalized trace with an
existing mew implement_v2 artifact root.  It is intentionally artifact-only:
it does not run Harbor, call models, or feed decisions back into live loop
behavior.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import json
import re
import shlex
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..agent_trace import (
    normalize_harbor_agent_trace,
    normalize_mew_implement_v2_history,
    normalize_mew_native_response_transcript,
    normalize_mew_report,
    summarize_trace,
)

HOT_PATH_STEP_DIFF_SCHEMA_VERSION = 1
HOT_PATH_OBSERVABILITY_REPORT_KIND = "m6_24_hot_path_observability"
NOT_LIVE_POLICY = "Do not use this diagnostic to force a next action."

INTENT_CATEGORIES = (
    "source_scan",
    "source_read",
    "binary_probe",
    "disassembly_probe",
    "build_attempt",
    "runtime_verifier",
    "mutation",
    "process_poll",
    "delegated_explore",
    "dependency_probe",
    "finish",
    "other_probe",
    "unknown",
)
PROBE_INTENTS = frozenset(
    {
        "source_scan",
        "source_read",
        "binary_probe",
        "disassembly_probe",
        "dependency_probe",
        "build_attempt",
        "runtime_verifier",
        "delegated_explore",
        "other_probe",
    }
)
MUTATION_TOOLS = frozenset({"apply_patch", "edit_file", "write_file"})
PROCESS_POLL_TOOLS = frozenset({"poll_command", "read_command_output", "write_stdin", "bashoutput"})
SOURCE_READ_TOOLS = frozenset({"read_file", "read"})
SOURCE_SCAN_TOOLS = frozenset({"search_text", "glob", "inspect_dir", "list_dir", "ls"})
SOURCE_TREE_PATH_PREFIXES = (
    "src/",
    "lib/",
    "app/",
    "include/",
    "test/",
    "tests/",
    "script/",
    "scripts/",
)
SOURCE_FILE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".hh",
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".kts",
        ".rb",
        ".php",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".pl",
        ".pm",
        ".lua",
        ".swift",
        ".scala",
        ".cs",
        ".fs",
        ".fsx",
        ".ml",
        ".mli",
        ".ex",
        ".exs",
        ".erl",
        ".hrl",
        ".clj",
        ".cljs",
        ".sql",
        ".html",
        ".css",
        ".scss",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".md",
    }
)


@dataclass(frozen=True)
class TraceBundle:
    agent: str
    root: Path
    events: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    sources: dict[str, str]
    warnings: tuple[str, ...] = ()
    artifact_summary: dict[str, Any] | None = None


def analyze_hot_path_step_diff(
    *,
    codex_reference_root: object,
    mew_artifact_root: object,
    claude_code_reference_root: object | None = None,
) -> dict[str, object]:
    """Build a sidecar step-diff report from existing artifact roots."""

    codex = _load_codex_bundle(Path(str(codex_reference_root)).expanduser())
    claude_code = (
        _load_claude_code_bundle(Path(str(claude_code_reference_root)).expanduser())
        if claude_code_reference_root is not None
        else None
    )
    mew = _load_mew_bundle(Path(str(mew_artifact_root)).expanduser())
    codex_steps = _normalize_tool_steps(codex.events, agent="codex")
    claude_code_steps = _normalize_tool_steps(claude_code.events, agent="claude_code") if claude_code else []
    mew_steps = _normalize_tool_steps(mew.events, agent="mew")
    codex_step_summary = _step_summary(codex_steps)
    claude_code_step_summary = _step_summary(claude_code_steps) if claude_code else {}
    mew_step_summary = _step_summary(mew_steps)
    repeated_probe_families = {
        "codex": _repeated_probe_families(codex_steps),
        "claude_code": _repeated_probe_families(claude_code_steps) if claude_code else _empty_repeated_probe_families(),
        "mew": _repeated_probe_families(mew_steps),
    }
    h0_readiness_diagnostics = _h0_readiness_diagnostics(
        agent_inputs={
            "codex": (codex, codex_steps, codex_step_summary),
            **({"claude_code": (claude_code, claude_code_steps, claude_code_step_summary)} if claude_code else {}),
            "mew": (mew, mew_steps, mew_step_summary),
        },
        repeated_probe_families=repeated_probe_families,
    )
    possible_first_patch_opportunities = _possible_first_patch_opportunities(
        codex_steps=codex_steps,
        mew_steps=mew_steps,
        codex_summary=codex_step_summary,
        mew_summary=mew_step_summary,
        repeated_mew=repeated_probe_families["mew"],
    )
    divergence_summary = _divergence_summary(
        codex_summary=codex_step_summary,
        mew_summary=mew_step_summary,
        repeated_mew=repeated_probe_families["mew"],
        opportunities=possible_first_patch_opportunities,
    )
    agents = {
        "codex": _agent_report(codex, codex_steps, codex_step_summary),
        "mew": _agent_report(mew, mew_steps, mew_step_summary),
    }
    if claude_code is not None:
        agents["claude_code"] = _agent_report(claude_code, claude_code_steps, claude_code_step_summary)
    return {
        "schema_version": HOT_PATH_STEP_DIFF_SCHEMA_VERSION,
        "report_kind": HOT_PATH_OBSERVABILITY_REPORT_KIND,
        "sidecar_only": True,
        "intent_categories": list(INTENT_CATEGORIES),
        "comparison_policy": {
            "primary_reference_agent": "codex",
            "candidate_agent": "mew",
            "selection_reason": "default_codex_reference",
            "explicit_selection": False,
        },
        "inputs": {
            "codex_reference_root": str(codex.root.resolve(strict=False)),
            "claude_code_reference_root": str(claude_code.root.resolve(strict=False)) if claude_code else None,
            "mew_artifact_root": str(mew.root.resolve(strict=False)),
            "codex": _input_status(codex),
            "claude_code": _input_status(claude_code) if claude_code else {"status": "missing", "sources": {}},
            "mew": _input_status(mew),
        },
        "sources": {
            "codex": codex.sources,
            "claude_code": claude_code.sources if claude_code else {},
            "mew": mew.sources,
        },
        "artifact_warnings": {
            "codex": list(codex.warnings),
            "claude_code": list(claude_code.warnings) if claude_code else [],
            "mew": list(mew.warnings),
        },
        "warnings": [
            *(f"codex: {warning}" for warning in codex.warnings),
            *(f"claude_code: {warning}" for warning in (claude_code.warnings if claude_code else ())),
            *(f"mew: {warning}" for warning in mew.warnings),
        ],
        "summary": {
            "codex": _combined_summary(codex.summary, codex_step_summary, codex.artifact_summary or {}),
            **(
                {
                    "claude_code": _combined_summary(
                        claude_code.summary,
                        claude_code_step_summary,
                        claude_code.artifact_summary or {},
                    )
                }
                if claude_code
                else {}
            ),
            "mew": _combined_summary(mew.summary, mew_step_summary, mew.artifact_summary or {}),
        },
        "agents": agents,
        "pairwise_comparisons": _pairwise_comparisons(
            reference_summaries={
                "codex": codex_step_summary,
                **({"claude_code": claude_code_step_summary} if claude_code else {}),
            },
            candidate_summary=mew_step_summary,
            readiness_diagnostics=h0_readiness_diagnostics,
        ),
        "normalized_codex_steps": codex_steps,
        "normalized_claude_code_steps": claude_code_steps,
        "normalized_mew_steps": mew_steps,
        "h0_readiness_diagnostics": h0_readiness_diagnostics,
        "repeated_probe_family_diagnostics": repeated_probe_families,
        "possible_first_patch_opportunity_diagnostics": possible_first_patch_opportunities,
        "divergence_summary": divergence_summary,
        "close_gate_inputs": {
            "no_live_tasks_run": True,
            "existing_artifacts_only": True,
            "provider_visible_behavior_changed": False,
        },
    }


def write_hot_path_step_diff_report(
    *,
    codex_reference_root: object,
    mew_artifact_root: object,
    out_json: object,
    out_md: object,
    claude_code_reference_root: object | None = None,
) -> dict[str, object]:
    """Build and write JSON plus Markdown step-diff reports."""

    report = analyze_hot_path_step_diff(
        codex_reference_root=codex_reference_root,
        claude_code_reference_root=claude_code_reference_root,
        mew_artifact_root=mew_artifact_root,
    )
    json_path = Path(str(out_json)).expanduser()
    md_path = Path(str(out_md)).expanduser()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(format_hot_path_step_diff_markdown(report) + "\n", encoding="utf-8")
    return report


def format_hot_path_step_diff_markdown(report: Mapping[str, object]) -> str:
    """Render a compact Markdown view for handoff and review."""

    summary = _mapping(report.get("summary"))
    codex_summary = _mapping(summary.get("codex"))
    claude_code_summary = _mapping(summary.get("claude_code"))
    mew_summary = _mapping(summary.get("mew"))
    lines = [
        "# M6.24 Hot-Path Observability",
        "",
        "Artifact-only sidecar analysis. This report does not affect live mew behavior.",
        "",
        "## Inputs",
        "",
        f"- Codex reference root: `{_markdown_escape(str(_mapping(report.get('inputs')).get('codex_reference_root') or ''))}`",
        f"- Claude Code reference root: `{_markdown_escape(str(_mapping(report.get('inputs')).get('claude_code_reference_root') or ''))}`",
        f"- mew artifact root: `{_markdown_escape(str(_mapping(report.get('inputs')).get('mew_artifact_root') or ''))}`",
        "",
        "## Metric Summary",
        "",
        "| Metric | Codex reference | Claude Code reference | mew artifact |",
        "|---|---:|---:|---:|",
    ]
    for label, key in (
        ("Tool steps", "tool_step_count"),
        ("Probe count before first mutation", "probe_count_before_first_mutation"),
        ("Process polls before first mutation", "process_poll_count_before_first_mutation"),
        ("First mutation step", "first_mutation_step_index"),
        ("First mutation turn", "first_mutation_turn"),
        ("First verifier step", "first_verifier_step_index"),
        ("First verifier turn", "first_verifier_turn"),
        ("Total seconds", "total_seconds"),
    ):
        lines.append(
            f"| {label} | {_summary_cell(codex_summary.get(key))} | "
            f"{_summary_cell(claude_code_summary.get(key))} | {_summary_cell(mew_summary.get(key))} |"
        )

    lines.extend(["", "## H0 Readiness Diagnostics", ""])
    h0_agents = _mapping(_mapping(report.get("h0_readiness_diagnostics")).get("agents"))
    if not h0_agents:
        lines.append("- No H0 readiness diagnostics were emitted.")
    for agent in ("codex", "claude_code", "mew"):
        data = _mapping(h0_agents.get(agent))
        if not data:
            continue
        lines.append(
            f"- `{agent}` readiness step {_summary_cell(data.get('first_patch_readiness_step_index'))}, "
            f"readiness-to-mutation {_summary_cell(data.get('readiness_to_mutation_steps'))} step(s), "
            f"duplicate-after-readiness families "
            f"{len([item for item in data.get('duplicate_exploration_after_readiness') or [] if isinstance(item, Mapping)])}."
        )

    lines.extend(["", "## Pairwise Comparisons", ""])
    comparisons = [item for item in report.get("pairwise_comparisons") or [] if isinstance(item, Mapping)]
    if comparisons:
        lines.extend(
            [
                "| Comparison | Comparable | Probe delta | First mutation delta | Readiness-to-mutation delta |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for item in comparisons:
            deltas = _mapping(item.get("metric_deltas"))
            probe_delta = _mapping(deltas.get("probe_count_before_mutation")).get("delta")
            mutation_delta = _mapping(deltas.get("first_mutation_step_index")).get("delta")
            readiness_delta = _mapping(deltas.get("readiness_to_mutation_steps")).get("delta")
            lines.append(
                f"| `{_markdown_escape(str(item.get('comparison_id') or ''))}` | "
                f"{_summary_cell(item.get('comparable'))} | "
                f"{_summary_cell(probe_delta)} | {_summary_cell(mutation_delta)} | {_summary_cell(readiness_delta)} |"
            )
    else:
        lines.append("- No pairwise comparisons were emitted.")

    lines.extend(["", "## Divergence Summary", ""])
    for item in report.get("divergence_summary") or []:
        lines.append(f"- {_markdown_escape(str(item))}")
    if not report.get("divergence_summary"):
        lines.append("- No concise divergence signal was detected.")

    lines.extend(["", "## First-Patch Opportunities", ""])
    opportunities = [item for item in report.get("possible_first_patch_opportunity_diagnostics") or [] if isinstance(item, Mapping)]
    if not opportunities:
        lines.append("- No first-patch opportunity diagnostic was detected.")
    for item in opportunities:
        diagnostic_id = str(item.get("code") or item.get("kind") or "diagnostic")
        lines.append(f"- `{_markdown_escape(diagnostic_id)}`: {_markdown_escape(str(item.get('message') or ''))}")
        for basis in item.get("basis") or []:
            if not isinstance(basis, Mapping):
                continue
            lines.append(
                "  - "
                f"{_markdown_escape(str(basis.get('agent') or ''))} step {_summary_cell(basis.get('step_index'))} "
                f"`{_markdown_escape(str(basis.get('intent') or ''))}` "
                f"`{_markdown_escape(str(basis.get('tool') or ''))}`: "
                f"{_markdown_escape(_truncate(str(basis.get('summary') or ''), 160))}"
            )

    lines.extend(["", "## Repeated Probe Families", ""])
    for agent in ("codex", "claude_code", "mew"):
        diagnostics = _mapping(_mapping(report.get("repeated_probe_family_diagnostics")).get(agent))
        if not diagnostics and agent == "claude_code":
            continue
        before = [item for item in diagnostics.get("before_first_mutation") or [] if isinstance(item, Mapping)]
        all_repeats = [item for item in diagnostics.get("all") or [] if isinstance(item, Mapping)]
        lines.append(f"### {agent}")
        if not before and not all_repeats:
            lines.append("")
            lines.append("No repeated probe families detected.")
            lines.append("")
            continue
        lines.extend(["", "| Scope | Family | Count | Example steps |", "|---|---|---:|---|"])
        for scope, rows in (("before first mutation", before), ("full trace", all_repeats)):
            for row in rows:
                examples = ", ".join(str(step) for step in row.get("step_indexes") or [])
                lines.append(
                    f"| {scope} | `{_markdown_escape(str(row.get('family') or ''))}` | "
                    f"{_summary_cell(row.get('count'))} | {_markdown_escape(examples)} |"
                )
        lines.append("")

    lines.extend(["## Tool/Result Pairing", ""])
    agents = _mapping(report.get("agents"))
    lines.extend(["| Agent | Paired | Missing result | Missing call | Unknown |", "|---|---:|---:|---:|---:|"])
    for agent in ("codex", "claude_code", "mew"):
        metrics = _mapping(_mapping(agents.get(agent)).get("metrics"))
        pairing = _mapping(metrics.get("tool_result_pairing"))
        lines.append(
            f"| `{agent}` | {_summary_cell(pairing.get('paired'))} | "
            f"{_summary_cell(pairing.get('missing_result'))} | {_summary_cell(pairing.get('missing_call'))} | "
            f"{_summary_cell(pairing.get('unknown'))} |"
        )

    lines.extend(["", "## Prompt And Input Size", ""])
    lines.extend(["| Agent | Request count | First request chars | Max request chars |", "|---|---:|---:|---:|"])
    for agent in ("codex", "claude_code", "mew"):
        metrics = _mapping(_mapping(agents.get(agent)).get("metrics"))
        prompt = _mapping(metrics.get("prompt_input_size"))
        lines.append(
            f"| `{agent}` | {_summary_cell(prompt.get('request_count'))} | "
            f"{_summary_cell(prompt.get('first_request_chars'))} | {_summary_cell(prompt.get('max_request_chars'))} |"
        )

    lines.extend(["", "## Warnings", ""])
    warnings = [str(item) for item in report.get("warnings") or []]
    if warnings:
        lines.extend(f"- {_markdown_escape(item)}" for item in warnings)
    else:
        lines.append("- No report-level warnings.")

    lines.extend(["## Normalized Codex Steps", ""])
    _append_step_table(lines, report.get("normalized_codex_steps") or [])
    lines.extend(["", "## Normalized Claude Code Steps", ""])
    _append_step_table(lines, report.get("normalized_claude_code_steps") or [])
    lines.extend(["", "## Normalized mew Steps", ""])
    _append_step_table(lines, report.get("normalized_mew_steps") or [])
    return "\n".join(lines)


def _load_codex_bundle(root: Path) -> TraceBundle:
    return _load_reference_bundle(root=root, agent="codex", normalize_agent="codex")


def _load_claude_code_bundle(root: Path) -> TraceBundle:
    return _load_reference_bundle(root=root, agent="claude_code", normalize_agent="claude")


def _load_reference_bundle(*, root: Path, agent: str, normalize_agent: str) -> TraceBundle:
    warnings: list[str] = []
    trace_dir = _resolve_normalized_trace_dir(root, expected_agent=normalize_agent)
    events: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    sources: dict[str, str] = {}
    if trace_dir is not None:
        summary_path = trace_dir / "summary.json"
        event_path = _resolve_trace_event_path(trace_dir)
        if summary_path.is_file():
            summary = _load_json_mapping(summary_path)
            sources["summary"] = str(summary_path.resolve(strict=False))
        if event_path is not None and event_path.is_file():
            events = _trace_rows(event_path)
            sources["events"] = str(event_path.resolve(strict=False))
    if not events:
        try:
            events, generated_summary = normalize_harbor_agent_trace(agent=normalize_agent, task_dir=root)
            summary = summary or generated_summary
            sources["fallback_task_dir"] = str(root.resolve(strict=False))
        except Exception as exc:  # noqa: BLE001 - artifact reader should degrade with warnings.
            warnings.append(f"could not normalize {agent} task dir fallback: {exc}")
    if not summary:
        summary = summarize_trace(agent=normalize_agent, events=events)
    if not events:
        warnings.append(f"no {agent} events were found")
    return TraceBundle(agent=agent, root=root, events=tuple(events), summary=summary, sources=sources, warnings=tuple(warnings))


def _load_mew_bundle(root: Path) -> TraceBundle:
    warnings: list[str] = []
    sources: dict[str, str] = {}
    artifact_summary: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    trace_summary_path: Path | None = None

    transcript_path = _resolve_first_existing(
        root,
        relative_candidates=(
            "response_transcript.json",
            "implement_v2/response_transcript.json",
        ),
        basename="response_transcript.json",
    )
    if transcript_path is not None:
        manifest_path = _resolve_manifest_path(root, transcript_path)
        report_metrics = _report_metrics(_resolve_first_existing(root, relative_candidates=("mew-report.json",), basename="mew-report.json"))
        try:
            events = normalize_mew_native_response_transcript(
                transcript_path=transcript_path,
                manifest_path=manifest_path,
                report_metrics=report_metrics,
            )
            sources["response_transcript"] = str(transcript_path.resolve(strict=False))
            if manifest_path is not None:
                sources["proof_manifest"] = str(manifest_path.resolve(strict=False))
        except Exception as exc:  # noqa: BLE001 - sidecar diagnostics should keep reading other artifacts.
            warnings.append(f"could not normalize native response transcript: {exc}")

    if not events:
        report_path = _resolve_first_existing(root, relative_candidates=("mew-report.json",), basename="mew-report.json")
        if report_path is not None:
            try:
                events = normalize_mew_report(report_path)
                sources["mew_report"] = str(report_path.resolve(strict=False))
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"could not normalize mew report: {exc}")

    if not events:
        history_path = _resolve_first_existing(
            root,
            relative_candidates=("implement_v2/history.json", "history.json"),
            basename="history.json",
        )
        if history_path is not None:
            report_path = _resolve_first_existing(root, relative_candidates=("mew-report.json",), basename="mew-report.json")
            try:
                events = normalize_mew_implement_v2_history(history_path=history_path, report_path=report_path)
                sources["history"] = str(history_path.resolve(strict=False))
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"could not normalize implement_v2 history: {exc}")

    if not events:
        trace_dir = _resolve_normalized_trace_dir(root, expected_agent="mew")
        if trace_dir is not None:
            event_path = _resolve_trace_event_path(trace_dir)
            if event_path is not None and event_path.is_file():
                events = _trace_rows(event_path)
                sources["normalized_trace_events"] = str(event_path.resolve(strict=False))
            if (trace_dir / "summary.json").is_file():
                trace_summary_path = trace_dir / "summary.json"
                sources["normalized_trace_summary"] = str(trace_summary_path.resolve(strict=False))

    command_transcript_path = _resolve_first_existing(
        root,
        relative_candidates=("command-transcript.json",),
        basename="command-transcript.json",
    )
    command_transcript = _load_json_mapping(command_transcript_path) if command_transcript_path is not None else {}
    if command_transcript_path is not None:
        sources["command_transcript"] = str(command_transcript_path.resolve(strict=False))

    transcript_metrics_path = _resolve_first_existing(
        root,
        relative_candidates=("transcript_metrics.json", "implement_v2/transcript_metrics.json"),
        basename="transcript_metrics.json",
    )
    if transcript_metrics_path is not None:
        artifact_summary["transcript_metrics"] = _compact_transcript_metrics(_load_json_mapping(transcript_metrics_path))
        sources["transcript_metrics"] = str(transcript_metrics_path.resolve(strict=False))

    provider_requests_path = _resolve_first_existing(
        root,
        relative_candidates=("native-provider-requests.json", "implement_v2/native-provider-requests.json"),
        basename="native-provider-requests.json",
    )
    if provider_requests_path is not None:
        artifact_summary["native_provider_requests"] = _native_provider_request_summary(_load_json_any(provider_requests_path))
        sources["native_provider_requests"] = str(provider_requests_path.resolve(strict=False))

    if not events:
        warnings.append("no mew response transcript, report, or history events were found")
    summary = _load_json_mapping(trace_summary_path) if trace_summary_path is not None else {}
    if not summary:
        summary = summarize_trace(agent="mew", events=events, transcript=command_transcript)
    return TraceBundle(
        agent="mew",
        root=root,
        events=tuple(events),
        summary=summary,
        sources=sources,
        warnings=tuple(warnings),
        artifact_summary=artifact_summary,
    )


def _normalize_tool_steps(events: Sequence[Mapping[str, Any]], *, agent: str) -> list[dict[str, object]]:
    groups: "OrderedDict[tuple[object, ...], dict[str, Any]]" = OrderedDict()
    for event_index, event in enumerate(events, 1):
        if event.get("kind") != "tool_call":
            continue
        key = _tool_group_key(event, event_index)
        group = groups.setdefault(key, {"events": [], "first_event_index": event_index})
        group["events"].append(dict(event))
    steps: list[dict[str, object]] = []
    for step_index, group in enumerate(groups.values(), 1):
        grouped_events = [event for event in group["events"] if isinstance(event, Mapping)]
        started = next((event for event in grouped_events if event.get("phase") == "started"), grouped_events[0])
        completed = next((event for event in reversed(grouped_events) if event.get("phase") == "completed"), grouped_events[-1])
        has_started = any(event.get("phase") == "started" for event in grouped_events)
        has_completed = any(event.get("phase") == "completed" for event in grouped_events)
        pairing_status = _pairing_status(has_started=has_started, has_completed=has_completed, tool_id=str(started.get("id") or ""))
        merged = _merge_step_events(started, completed)
        intent, basis = _classify_intent(merged)
        family = _probe_family(merged, intent=intent)
        tool_family = _tool_family(merged, intent=intent)
        elapsed_ms = merged.get("elapsed_ms") if isinstance(merged.get("elapsed_ms"), int) else None
        duration_ms = merged.get("duration_ms") if isinstance(merged.get("duration_ms"), int) else None
        step = {
            "schema_version": 1,
            "index": step_index,
            "step_index": step_index,
            "agent": agent,
            "agent_context": "main",
            "turn": _int_or_none(merged.get("step_id")),
            "turn_index": _int_or_none(merged.get("step_id")),
            "sequence": _int_or_none(merged.get("sequence_index")),
            "tool": str(merged.get("tool") or ""),
            "tool_name": str(merged.get("tool") or ""),
            "tool_family": tool_family,
            "tool_id": str(merged.get("id") or ""),
            "source_event_id": str(merged.get("id") or ""),
            "intent": intent,
            "is_probe": intent in PROBE_INTENTS,
            "is_mutation": intent == "mutation",
            "is_verifier": intent == "runtime_verifier",
            "is_finish": intent == "finish",
            "paired_result_id": str(merged.get("id") or "") if pairing_status == "paired" else "",
            "pairing_status": pairing_status,
            "probe_family": family,
            "summary": _truncate(str(merged.get("summary") or ""), 500),
            "command": _truncate(_command_text(merged), 500),
            "status": str(merged.get("status") or ""),
            "exit_code": merged.get("exit_code") if isinstance(merged.get("exit_code"), int) else None,
            "elapsed_ms": elapsed_ms,
            "elapsed_seconds": _seconds_from_ms(merged.get("elapsed_ms")),
            "duration_ms": duration_ms,
            "duration_seconds": _seconds_from_ms(merged.get("duration_ms")),
            "source": str(merged.get("source") or ""),
            "source_path": str(merged.get("source") or ""),
            "line_number": _int_or_none(merged.get("line_number")),
            "source_line": _int_or_none(merged.get("line_number")),
            "target_paths": _extract_step_targets(merged),
            "input_chars": None,
            "output_chars": len(str(merged.get("summary") or "")),
            "original_token_count": None,
            "truncation": {"truncated": len(str(merged.get("summary") or "")) > 500, "reason": "summary_bound" if len(str(merged.get("summary") or "")) > 500 else None},
            "classification_basis": basis,
            "intent_basis": basis,
            "debug_only": True,
        }
        if _event_has_source_mutation(merged):
            step["source_mutation"] = _json_safe_mapping(merged.get("source_mutation"))
            kinds = merged.get("source_mutation_effect_kinds") or merged.get("side_effect_kinds")
            if isinstance(kinds, list):
                step["source_mutation_effect_kinds"] = [str(kind) for kind in kinds]
        steps.append(step)
    return steps


def _tool_group_key(event: Mapping[str, Any], event_index: int) -> tuple[object, ...]:
    tool_id = str(event.get("id") or "")
    tool = str(event.get("tool") or "")
    if tool_id:
        return ("id", tool, tool_id)
    source = str(event.get("source") or "")
    return (
        "position",
        tool,
        source,
        event.get("line_number"),
        event.get("step_id"),
        event.get("sequence_index"),
        event_index if event.get("phase") not in {"started", "completed"} else "",
    )


def _merge_step_events(started: Mapping[str, Any], completed: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(started)
    for key, value in completed.items():
        if key == "arguments" and isinstance(value, Mapping):
            arguments = dict(merged.get("arguments") or {}) if isinstance(merged.get("arguments"), Mapping) else {}
            arguments.update(dict(value))
            merged[key] = arguments
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _pairing_status(*, has_started: bool, has_completed: bool, tool_id: str) -> str:
    if not tool_id:
        return "unknown"
    if has_started and has_completed:
        return "paired"
    if has_started:
        return "missing_result"
    if has_completed:
        return "missing_call"
    return "unknown"


def _classify_intent(step: Mapping[str, Any]) -> tuple[str, list[str]]:
    tool = str(step.get("tool") or "").casefold()
    text = _step_text(step)
    command = _command_text(step).casefold()
    arguments = step.get("arguments") if isinstance(step.get("arguments"), Mapping) else {}
    contract = step.get("execution_contract") if isinstance(step.get("execution_contract"), Mapping) else {}

    if tool in {"finish", "finish_call"}:
        return "finish", [f"tool={tool}"]
    if tool in {"agent", "explore"}:
        return "delegated_explore", [f"tool={tool}"]
    if tool in MUTATION_TOOLS:
        return "mutation", [f"tool={tool}"]
    if _event_has_source_mutation(step):
        return "mutation", ["mutation tool or source_mutation sidecar", "source_mutation_detected"]
    if tool in PROCESS_POLL_TOOLS:
        return "process_poll", [f"tool={tool}"]
    if _looks_like_process_poll(command):
        return "process_poll", ["command_process_poll_pattern"]
    dependency_basis = _dependency_probe_basis(command)
    if dependency_basis:
        return "dependency_probe", dependency_basis
    binary_script_basis = _binary_analysis_script_basis(command)
    if binary_script_basis:
        return "binary_probe", binary_script_basis

    verifier_basis = _runtime_verifier_basis(tool=tool, text=text, command=command, arguments=arguments, contract=contract)
    if verifier_basis:
        return "runtime_verifier", verifier_basis

    build_basis = _build_attempt_basis(command)
    if build_basis:
        return "build_attempt", build_basis

    disassembly_basis = _regex_basis(command, r"\b(?:llvm-)?objdump\b|\bndisasm\b|\br2\b|\bradare2\b|\bdisassemble\b|\bdisas\b")
    if disassembly_basis:
        return "disassembly_probe", [f"command_regex={disassembly_basis}"]
    binary_basis = _regex_basis(command, r"\b(?:file|strings|readelf|nm|ldd|otool|xxd|hexdump)\b")
    if binary_basis:
        return "binary_probe", [f"command_regex={binary_basis}"]
    if tool in SOURCE_READ_TOOLS:
        return "source_read", [f"tool={tool}"]
    source_read_basis = _regex_basis(command, r"\b(?:cat|head|tail|nl|less)\b|\bsed\s+-n\b|open\([^)]*\)\.read\(")
    if source_read_basis:
        return "source_read", [f"command_regex={source_read_basis}"]
    if tool in SOURCE_SCAN_TOOLS:
        return "source_scan", [f"tool={tool}"]
    source_scan_basis = _regex_basis(command, r"\b(?:rg|grep|git\s+grep|find|fd|ls|tree)\b")
    if source_scan_basis:
        return "source_scan", [f"command_regex={source_scan_basis}"]
    return "other_probe", ["fallback=other_probe"]


def _runtime_verifier_basis(
    *,
    tool: str,
    text: str,
    command: str,
    arguments: Mapping[str, object],
    contract: Mapping[str, object],
) -> list[str]:
    basis: list[str] = []
    if tool in {"run_tests", "verifier", "strict_verifier"}:
        basis.append(f"tool={tool}")
    command_intent = str(arguments.get("command_intent") or arguments.get("intent") or "").casefold()
    if command_intent in {"verify", "verifier", "test", "acceptance"}:
        basis.append(f"command_intent={command_intent}")
    for key in ("proof_role", "acceptance_kind", "stage", "purpose", "role"):
        value = str(contract.get(key) or "").casefold()
        if value in {"verifier", "acceptance", "proof", "verify", "verification", "test", "final_proof"}:
            basis.append(f"execution_contract.{key}={value}")
    regex = _regex_basis(
        command or text,
        r"\b(?:pytest|tox|nox|cargo\s+test|npm\s+test|pnpm\s+test|yarn\s+test|go\s+test|unittest)\b"
        r"|\bmake\s+(?:test|check|verify)\b|\bninja\s+test\b"
        r"|\b(?:verify|verifier)\b|\bassert\b|\bdiff\b|\bcmp\b|\bgrep\s+-[A-Za-z]*q",
    )
    if regex:
        basis.append(f"command_regex={regex}")
    if _regex_basis(command, r"\b--version\b|\bwhich\b|\bcommand\s+-v\b|\btype\s+-p\b"):
        return basis
    if _regex_basis(command, r"^(?:\S*/)?(?:node|python\d*|ruby|perl|java|bash|sh)\s+\S+"):
        if not _regex_basis(command, r"open\([^)]*\)\.read\(|\b(?:cat|head|tail|sed|rg|grep)\b"):
            basis.append("command_executes_runtime")
    return basis


def _build_attempt_basis(command: str) -> list[str]:
    regex = _regex_basis(
        command,
        r"\bmake\b|\bninja\b|\bcmake\b|\b(?:gcc|g\+\+|clang|clang\+\+|cc)\b|"
        r"\bcargo\s+build\b|\bgo\s+build\b|\bnpm\s+run\s+build\b|\bpnpm\s+build\b|"
        r"\byarn\s+build\b|\bmvn\s+package\b|\bgradle\s+build\b|\bpip\s+install\b|"
        r"\bpython\d*\s+setup\.py\s+build\b",
    )
    return [f"command_regex={regex}"] if regex else []


def _dependency_probe_basis(command: str) -> list[str]:
    if not command:
        return []
    parts = [
        part.strip()
        for part in re.split(r"\s*(?:&&|\|\||;|\n)\s*", command)
        if part.strip() and part.strip() != "true"
    ]
    if not parts:
        return []
    dependency_parts = 0
    for part in parts:
        if re.fullmatch(r"(?:which|command\s+-v|type\s+-p)\s+\S+", part):
            dependency_parts += 1
            continue
        if re.fullmatch(r"\S+\s+--version", part):
            dependency_parts += 1
            continue
        if re.fullmatch(r"pkg-config\s+--modversion\s+\S+", part):
            dependency_parts += 1
            continue
        return []
    return [f"dependency_probe_parts={dependency_parts}"]


def _command_has_write_pattern(command: str) -> bool:
    if not command:
        return False
    detection_command = _strip_heredoc_bodies(command)
    shell_surface = _strip_shell_literals(detection_command)
    if _invokes_apply_patch(shell_surface):
        return True
    if re.search(r"\b(?:sed|perl)\s+-[A-Za-z]*i[A-Za-z]*\b", shell_surface):
        return True
    if re.search(r"open\([^)]*,\s*['\"][wa]", detection_command) or re.search(
        r"\b(?:write_text|write_bytes|writefilesync|writefile)\s*\(",
        detection_command,
    ):
        return True
    targets = [*_shell_redirection_targets(detection_command), *_tee_write_targets(detection_command)]
    return any(_looks_like_source_write_target(target) for target in targets)


def _strip_heredoc_bodies(command: str) -> str:
    lines = command.splitlines()
    if not lines:
        return command
    output: list[str] = []
    pending: list[str] = []
    for line in lines:
        if pending:
            if line.strip() == pending[0]:
                pending.pop(0)
                output.append("")
            continue
        output.append(line)
        pending.extend(_heredoc_delimiters(line))
    return "\n".join(output)


def _heredoc_delimiters(line: str) -> list[str]:
    delimiters: list[str] = []
    for match in re.finditer(r"<<-?\s*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][A-Za-z0-9_]*))", line):
        delimiter = next((group for group in match.groups() if group), "")
        if delimiter:
            delimiters.append(delimiter)
    return delimiters


def _strip_shell_literals(command: str) -> str:
    chars: list[str] = []
    quote = ""
    escaped = False
    for char in command:
        if escaped:
            chars.append(" " if quote else char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            chars.append(" ")
            continue
        if quote:
            if char == quote:
                quote = ""
            chars.append(" ")
            continue
        if char in {"'", '"', "`"}:
            quote = char
            chars.append(" ")
            continue
        chars.append(char)
    return "".join(chars)


def _invokes_apply_patch(shell_surface: str) -> bool:
    return bool(re.search(r"(?:^|[;&|]\s*)(?:\S*/)?apply_patch(?:\s|$|<)", shell_surface))


def _binary_analysis_script_basis(command: str) -> list[str]:
    if not command:
        return []
    if not re.search(r"^(?:\S*/)?(?:node|python\d*|ruby|perl)\s+", command):
        return []
    if not re.search(r"\b(?:readfilesync|read_file|readbytes|buffer|uint8array|dataview|struct\.unpack)\b", command):
        return []
    if not re.search(r">>>|>>|<<|0x[0-9a-f]+|\b(?:elf|opcode|binary|byte|word|endianness)\b", command):
        return []
    return ["script_binary_analysis_pattern"]


def _shell_redirection_targets(command: str) -> list[str]:
    targets: list[str] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if quote:
            if char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char != ">":
            index += 1
            continue

        run_end = index
        while run_end < len(command) and command[run_end] == ">":
            run_end += 1
        redirection_width = run_end - index
        next_char = command[run_end] if run_end < len(command) else ""
        if redirection_width > 2 or next_char == "=":
            index = run_end
            continue
        target_start = run_end
        while target_start < len(command) and command[target_start].isspace():
            target_start += 1
        if target_start < len(command) and command[target_start] == "&":
            index = target_start + 1
            continue
        target, index = _read_shell_word(command, target_start)
        if target:
            targets.append(target)
    return targets


def _read_shell_word(command: str, start: int) -> tuple[str, int]:
    index = start
    while index < len(command) and command[index].isspace():
        index += 1
    chars: list[str] = []
    quote = ""
    escaped = False
    while index < len(command):
        char = command[index]
        if escaped:
            chars.append(char)
            escaped = False
            index += 1
            continue
        if quote:
            if char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = ""
            else:
                chars.append(char)
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char.isspace() or char in {";", "|", "&", "<", ">", "(", ")"}:
            break
        chars.append(char)
        index += 1
    return "".join(chars), index


def _tee_write_targets(command: str) -> list[str]:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return []
    targets: list[str] = []
    index = 0
    separators = {"|", ";", "&&", "||"}
    while index < len(tokens):
        token = tokens[index].rsplit("/", 1)[-1]
        if token != "tee":
            index += 1
            continue
        index += 1
        while index < len(tokens) and tokens[index].startswith("-"):
            index += 1
        while index < len(tokens) and tokens[index] not in separators:
            targets.append(tokens[index])
            index += 1
    return targets


def _looks_like_source_write_target(target: str) -> bool:
    target = target.strip()
    if not target:
        return False
    if target.startswith("&") or target.startswith("$") or target.startswith("<(") or target.startswith(">("):
        return False
    target = target.strip("'\"")
    if target in {"-", "/dev/null", "/dev/stdout", "/dev/stderr"}:
        return False
    if target.startswith(("/dev/", "/proc/", "/sys/", "/tmp/", "/var/tmp/")):
        return False
    normalized = target.lstrip("./")
    if not normalized:
        return False
    if normalized.startswith(SOURCE_TREE_PATH_PREFIXES):
        return True
    return Path(normalized).suffix.casefold() in SOURCE_FILE_SUFFIXES


def _looks_like_process_poll(command: str) -> bool:
    return bool(command and re.search(r"\b(?:ps|pgrep|jobs)\b|\btail\s+-f\b|\bwait\b", command))


def _probe_family(step: Mapping[str, object], *, intent: str) -> str:
    if intent not in PROBE_INTENTS and intent != "process_poll":
        return ""
    tool = str(step.get("tool") or "tool")
    command = _command_text(step) or str(step.get("command") or "")
    if intent == "source_read":
        path = _extract_step_target(step)
        return f"{intent}:{path or tool}"
    verb = _command_verb(command) if command else ""
    return f"{intent}:{verb or tool}"


def _tool_family(step: Mapping[str, object], *, intent: str) -> str:
    command = _command_text(step).casefold()
    tool = str(step.get("tool") or "").casefold()
    if intent == "mutation":
        return "mutation"
    if intent == "runtime_verifier":
        return "runtime_verifier"
    if intent == "build_attempt":
        return "build"
    if intent == "process_poll":
        return "process_poll"
    if intent == "finish":
        return "finish"
    if intent == "delegated_explore":
        return "delegated_explore"
    if intent == "dependency_probe":
        return "dependency_check"
    if intent == "disassembly_probe":
        return "disassembly"
    if intent == "binary_probe":
        if _regex_basis(command, r"\b(?:nm|readelf|otool)\b|\bmap\b|\bsymbol\b"):
            return "symbol_lookup"
        return "binary_metadata"
    if intent == "source_read":
        return "file_read"
    if intent == "source_scan":
        if tool in {"glob", "inspect_dir", "list_dir", "ls"} or _regex_basis(command, r"\b(?:find|fd|ls|tree)\b"):
            return "source_listing"
        return "text_search"
    if intent == "other_probe":
        if _regex_basis(command, r"\b(?:which|command\s+-v|python\d*\s+--version|node\s+--version|npm\s+--version)\b"):
            return "dependency_check"
        return "other_probe"
    return "unknown"


def _step_summary(steps: Sequence[Mapping[str, object]]) -> dict[str, object]:
    first_mutation = _first_step(steps, lambda step: step.get("intent") == "mutation")
    first_apply_patch_or_write = _first_step(
        steps,
        lambda step: str(step.get("tool") or "").casefold() in MUTATION_TOOLS,
    )
    first_verifier = _first_step(steps, lambda step: step.get("intent") == "runtime_verifier")
    before_first_mutation = _steps_before(steps, first_mutation)
    intent_counts = Counter(str(step.get("intent") or "") for step in steps)
    tool_counts = Counter(str(step.get("tool") or "") for step in steps)
    before_intent_counts = Counter(str(step.get("intent") or "") for step in before_first_mutation)
    return {
        "tool_step_count": len(steps),
        "intent_counts": dict(sorted(intent_counts.items())),
        "tool_counts": dict(sorted(tool_counts.items())),
        "mutation_count": intent_counts.get("mutation", 0),
        "first_mutation": _step_citation(first_mutation),
        "first_mutation_step_index": first_mutation.get("index") if first_mutation else None,
        "first_mutation_turn": first_mutation.get("turn") if first_mutation else None,
        "first_mutation_tool": first_mutation.get("tool") if first_mutation else "",
        "first_mutation_elapsed_seconds": first_mutation.get("elapsed_seconds") if first_mutation else None,
        "first_apply_patch_or_write": _step_citation(first_apply_patch_or_write),
        "first_apply_patch_or_write_step_index": first_apply_patch_or_write.get("index") if first_apply_patch_or_write else None,
        "first_apply_patch_or_write_turn": first_apply_patch_or_write.get("turn") if first_apply_patch_or_write else None,
        "first_apply_patch_or_write_tool": first_apply_patch_or_write.get("tool") if first_apply_patch_or_write else "",
        "first_verifier": _step_citation(first_verifier),
        "first_verifier_step_index": first_verifier.get("index") if first_verifier else None,
        "first_verifier_turn": first_verifier.get("turn") if first_verifier else None,
        "first_verifier_tool": first_verifier.get("tool") if first_verifier else "",
        "first_verifier_elapsed_seconds": first_verifier.get("elapsed_seconds") if first_verifier else None,
        "probe_count_before_first_mutation": sum(1 for step in before_first_mutation if step.get("intent") in PROBE_INTENTS),
        "probe_intent_counts_before_first_mutation": {
            intent: before_intent_counts.get(intent, 0) for intent in sorted(PROBE_INTENTS)
        },
        "process_poll_count_before_first_mutation": sum(1 for step in before_first_mutation if step.get("intent") == "process_poll"),
    }


def _combined_summary(
    trace_summary: Mapping[str, object],
    step_summary: Mapping[str, object],
    artifact_summary: Mapping[str, object],
) -> dict[str, object]:
    result = dict(trace_summary)
    result.update(step_summary)
    if artifact_summary:
        result["artifact_summary"] = dict(artifact_summary)
    return result


def _input_status(bundle: TraceBundle | None) -> dict[str, object]:
    if bundle is None:
        return {"status": "missing", "sources": {}}
    if bundle.events:
        status = "partial" if bundle.warnings else "loaded"
    else:
        status = "missing"
    return {
        "root": str(bundle.root.resolve(strict=False)),
        "sources": dict(bundle.sources),
        "status": status,
        "warnings": list(bundle.warnings),
    }


def _agent_report(
    bundle: TraceBundle,
    steps: Sequence[Mapping[str, object]],
    step_summary: Mapping[str, object],
) -> dict[str, object]:
    return {
        "steps": list(steps),
        "metrics": _agent_metrics(bundle=bundle, steps=steps, step_summary=step_summary),
        "artifact_warnings": list(bundle.warnings),
    }


def _agent_metrics(
    *,
    bundle: TraceBundle,
    steps: Sequence[Mapping[str, object]],
    step_summary: Mapping[str, object],
) -> dict[str, object]:
    readiness = _first_patch_readiness(steps)
    first_mutation = _first_step(steps, lambda step: step.get("intent") == "mutation")
    return {
        **dict(step_summary),
        "first_tool": _step_citation(steps[0]) if steps else {},
        "first_patch_readiness": readiness,
        "readiness_to_mutation": _readiness_to_mutation(readiness=readiness, first_mutation=first_mutation),
        "implementation_constraint_families": _implementation_constraint_families(steps),
        "tool_result_pairing": _tool_result_pairing_counts(steps),
        "prompt_input_size": _prompt_input_size_metrics(bundle.artifact_summary or {}),
        "duplicate_exploration_after_readiness": _duplicate_exploration_after_readiness(
            steps=steps,
            readiness=readiness,
            first_mutation=first_mutation,
        ),
        "long_design_stalls_after_readiness": _long_design_stalls_after_readiness(
            events=bundle.events,
            readiness=readiness,
            first_mutation=first_mutation,
        ),
    }


def _empty_repeated_probe_families() -> dict[str, object]:
    return {"before_first_mutation": [], "all": [], "diagnostics": []}


def _tool_result_pairing_counts(steps: Sequence[Mapping[str, object]]) -> dict[str, int]:
    counts = {"paired": 0, "missing_result": 0, "missing_call": 0, "not_applicable": 0, "unknown": 0}
    for step in steps:
        status = str(step.get("pairing_status") or "unknown")
        if status not in counts:
            status = "unknown"
        counts[status] += 1
    return counts


def _prompt_input_size_metrics(artifact_summary: Mapping[str, object]) -> dict[str, object]:
    provider = artifact_summary.get("native_provider_requests") if isinstance(artifact_summary.get("native_provider_requests"), Mapping) else {}
    return {
        "request_count": provider.get("request_count") if isinstance(provider, Mapping) else None,
        "first_request_chars": None,
        "max_request_chars": None,
        "total_chars": None,
    }


def _pairwise_comparisons(
    *,
    reference_summaries: Mapping[str, Mapping[str, object]],
    candidate_summary: Mapping[str, object],
    readiness_diagnostics: Mapping[str, object],
) -> list[dict[str, object]]:
    comparisons: list[dict[str, object]] = []
    candidate_readiness = _mapping(_mapping(readiness_diagnostics.get("agents")).get("mew"))
    candidate_has_steps = bool(_int_or_none(candidate_summary.get("tool_step_count")))
    for reference_agent, reference_summary in reference_summaries.items():
        reference_readiness = _mapping(_mapping(readiness_diagnostics.get("agents")).get(reference_agent))
        reference_has_steps = bool(_int_or_none(reference_summary.get("tool_step_count")))
        comparable = reference_has_steps and candidate_has_steps
        comparisons.append(
            {
                "comparison_id": f"{reference_agent}_vs_mew",
                "reference_agent": reference_agent,
                "candidate_agent": "mew",
                "selection": "default_primary" if reference_agent == "codex" else "default_secondary",
                "comparable": comparable,
                "metric_deltas": {
                    "probe_count_before_mutation": _metric_delta(
                        reference_summary.get("probe_count_before_first_mutation"),
                        candidate_summary.get("probe_count_before_first_mutation"),
                        unit="steps",
                        comparable=comparable,
                    ),
                    "first_mutation_step_index": _metric_delta(
                        reference_summary.get("first_mutation_step_index"),
                        candidate_summary.get("first_mutation_step_index"),
                        unit="steps",
                        comparable=comparable,
                    ),
                    "readiness_to_mutation_steps": _metric_delta(
                        reference_readiness.get("readiness_to_mutation_steps"),
                        candidate_readiness.get("readiness_to_mutation_steps"),
                        unit="steps",
                        comparable=comparable,
                    ),
                },
                "warnings": [],
            }
        )
    return comparisons


def _metric_delta(reference_value: object, candidate_value: object, *, unit: str, comparable: bool = True) -> dict[str, object]:
    reference_number = _number_or_none(reference_value)
    candidate_number = _number_or_none(candidate_value)
    comparable = comparable and reference_number is not None and candidate_number is not None
    return {
        "reference_value": reference_value,
        "candidate_value": candidate_value,
        "delta": (candidate_number - reference_number) if comparable else None,
        "unit": unit,
        "comparable": comparable,
    }


def _h0_readiness_diagnostics(
    *,
    agent_inputs: Mapping[str, tuple[TraceBundle, Sequence[Mapping[str, object]], Mapping[str, object]]],
    repeated_probe_families: Mapping[str, object],
) -> dict[str, object]:
    agents: dict[str, object] = {}
    for agent, (_bundle, steps, _summary) in agent_inputs.items():
        readiness = _first_patch_readiness(steps)
        first_mutation = _first_step(steps, lambda step: step.get("intent") == "mutation")
        agents[agent] = {
            **readiness,
            **_readiness_to_mutation(readiness=readiness, first_mutation=first_mutation),
            "implementation_constraint_families": _implementation_constraint_families(steps),
            "duplicate_exploration_after_readiness": _duplicate_exploration_after_readiness(
                steps=steps,
                readiness=readiness,
                first_mutation=first_mutation,
            ),
            "long_design_stalls_after_readiness": _long_design_stalls_after_readiness(
                events=_bundle.events,
                readiness=readiness,
                first_mutation=first_mutation,
            ),
            "repeated_probe_families": _mapping(repeated_probe_families.get(agent)),
        }
    return {
        "diagnostic_only": True,
        "not_live_policy": "Do not feed readiness or next-action diagnostics into provider prompts or tool policy.",
        "agents": agents,
    }


def _first_patch_readiness(steps: Sequence[Mapping[str, object]]) -> dict[str, object]:
    first_mutation = _first_step(steps, lambda step: step.get("intent") == "mutation")
    first_mutation_index = _int_or_none(first_mutation.get("index")) if first_mutation is not None else None
    source_basis: Mapping[str, object] | None = None
    execution_basis: Mapping[str, object] | None = None
    distinct_families: set[str] = set()
    probe_count = 0
    for step in steps:
        step_index = _int_or_none(step.get("index"))
        if first_mutation_index is not None and step_index is not None and step_index >= first_mutation_index:
            break
        intent = str(step.get("intent") or "")
        if intent in PROBE_INTENTS:
            probe_count += 1
            family = str(step.get("tool_family") or step.get("probe_family") or intent)
            distinct_families.add(family)
        if source_basis is None and intent in {"source_scan", "source_read"}:
            source_basis = step
        if execution_basis is None and intent in {"runtime_verifier", "build_attempt", "binary_probe", "disassembly_probe"}:
            execution_basis = step
        has_source_only_readiness = source_basis is not None and probe_count >= 3 and len(distinct_families) >= 2
        has_source_and_execution_readiness = source_basis is not None and execution_basis is not None and probe_count >= 2
        if has_source_only_readiness or has_source_and_execution_readiness:
            return {
                "first_patch_readiness_step_index": step.get("index"),
                "first_patch_readiness_turn": step.get("turn"),
                "first_patch_readiness_elapsed_seconds": step.get("elapsed_seconds"),
                "first_patch_readiness_basis": [
                    _step_citation(source_basis),
                    _step_citation(execution_basis) if execution_basis is not None else {},
                    _step_citation(step),
                ],
                "first_patch_readiness_basis_kind": (
                    "source_plus_runtime_or_artifact_probe"
                    if execution_basis is not None
                    else "repeated_source_probe_constraint"
                ),
                "first_patch_readiness_probe_count": probe_count,
                "first_patch_readiness_family_count": len(distinct_families),
                "diagnostic_only": True,
            }
    if first_mutation is not None:
        return {
            "first_patch_readiness_step_index": first_mutation.get("index"),
            "first_patch_readiness_turn": first_mutation.get("turn"),
            "first_patch_readiness_elapsed_seconds": first_mutation.get("elapsed_seconds"),
            "first_patch_readiness_basis": [_step_citation(first_mutation)],
            "first_patch_readiness_basis_kind": "mutation_observed_proxy",
            "first_patch_readiness_probe_count": probe_count,
            "first_patch_readiness_family_count": len(distinct_families),
            "diagnostic_only": True,
        }
    return {
        "first_patch_readiness_step_index": None,
        "first_patch_readiness_turn": None,
        "first_patch_readiness_elapsed_seconds": None,
        "first_patch_readiness_basis": [],
        "first_patch_readiness_basis_kind": "insufficient_generic_evidence",
        "first_patch_readiness_probe_count": probe_count,
        "first_patch_readiness_family_count": len(distinct_families),
        "diagnostic_only": True,
    }


def _readiness_to_mutation(
    *,
    readiness: Mapping[str, object],
    first_mutation: Mapping[str, object] | None,
) -> dict[str, object]:
    readiness_step = _int_or_none(readiness.get("first_patch_readiness_step_index"))
    mutation_step = _int_or_none(first_mutation.get("index")) if first_mutation is not None else None
    readiness_seconds = _number_or_none(readiness.get("first_patch_readiness_elapsed_seconds"))
    mutation_seconds = _number_or_none(first_mutation.get("elapsed_seconds")) if first_mutation is not None else None
    step_delta = (mutation_step - readiness_step) if readiness_step is not None and mutation_step is not None else None
    seconds_delta = (
        round(mutation_seconds - readiness_seconds, 3)
        if readiness_seconds is not None and mutation_seconds is not None and mutation_seconds >= readiness_seconds
        else None
    )
    return {
        "readiness_to_mutation_steps": step_delta if step_delta is not None and step_delta >= 0 else None,
        "readiness_to_mutation_seconds": seconds_delta,
    }


def _implementation_constraint_families(steps: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    first_by_family: "OrderedDict[str, Mapping[str, object]]" = OrderedDict()
    counts: Counter[str] = Counter()
    for step in steps:
        if step.get("intent") not in PROBE_INTENTS:
            continue
        family = str(step.get("tool_family") or step.get("probe_family") or "")
        if not family:
            continue
        counts[family] += 1
        first_by_family.setdefault(family, step)
    return [
        {
            "family": family,
            "count": counts[family],
            "first_basis": _step_citation(step),
            "diagnostic_only": True,
        }
        for family, step in first_by_family.items()
    ]


def _duplicate_exploration_after_readiness(
    *,
    steps: Sequence[Mapping[str, object]],
    readiness: Mapping[str, object],
    first_mutation: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    readiness_step = _int_or_none(readiness.get("first_patch_readiness_step_index"))
    if readiness_step is None:
        return []
    mutation_step = _int_or_none(first_mutation.get("index")) if first_mutation is not None else None
    window = [
        step
        for step in steps
        if (_int_or_none(step.get("index")) or 0) > readiness_step
        and (mutation_step is None or (_int_or_none(step.get("index")) or 0) < mutation_step)
        and step.get("intent") in PROBE_INTENTS
    ]
    return _family_repeats(window)


def _long_design_stalls_after_readiness(
    *,
    events: Sequence[Mapping[str, object]],
    readiness: Mapping[str, object],
    first_mutation: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    readiness_turn = _int_or_none(readiness.get("first_patch_readiness_turn"))
    if readiness_turn is None:
        return []
    mutation_turn = _int_or_none(first_mutation.get("turn")) if first_mutation is not None else None
    stalls: list[dict[str, object]] = []
    for event in events:
        if event.get("kind") != "message":
            continue
        step_id = _int_or_none(event.get("step_id"))
        if step_id is None or step_id <= readiness_turn:
            continue
        if mutation_turn is not None and step_id >= mutation_turn:
            continue
        summary = str(event.get("summary") or "")
        metrics = event.get("model_metrics") if isinstance(event.get("model_metrics"), Mapping) else {}
        completion_tokens = _int_or_none(metrics.get("completion_tokens") or metrics.get("output_tokens"))
        if len(summary) < 1200 and (completion_tokens is None or completion_tokens < 8000):
            continue
        stalls.append(
            {
                "step_index": step_id,
                "summary_chars": len(summary),
                "completion_tokens": completion_tokens,
                "basis": _step_citation(
                    {
                        "agent": event.get("agent") or "",
                        "index": step_id,
                        "turn": step_id,
                        "tool": "message",
                        "tool_id": "",
                        "intent": "reasoning_or_message",
                        "summary": summary,
                        "classification_basis": ["long_message_after_readiness"],
                    }
                ),
                "diagnostic_only": True,
            }
        )
    return stalls


def _repeated_probe_families(steps: Sequence[Mapping[str, object]]) -> dict[str, object]:
    first_mutation = _first_step(steps, lambda step: step.get("intent") == "mutation")
    before_first_mutation = _steps_before(steps, first_mutation)
    diagnostics = _intent_repeats(before_first_mutation)
    return {
        "before_first_mutation": _family_repeats(before_first_mutation),
        "all": _family_repeats(steps),
        "diagnostics": diagnostics,
    }


def _intent_repeats(steps: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    by_intent: "OrderedDict[str, list[Mapping[str, object]]]" = OrderedDict()
    for step in steps:
        intent = str(step.get("intent") or "")
        if intent not in PROBE_INTENTS:
            continue
        by_intent.setdefault(intent, []).append(step)
    rows: list[dict[str, object]] = []
    for intent, intent_steps in by_intent.items():
        if len(intent_steps) <= 1:
            continue
        rows.append(
            {
                "intent": intent,
                "count": len(intent_steps),
                "before_first_mutation_count": len(intent_steps),
                "step_indexes": [step.get("index") for step in intent_steps],
                "basis": [_step_citation(step) for step in intent_steps[:3]],
            }
        )
    return rows


def _family_repeats(steps: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    families: "OrderedDict[str, list[Mapping[str, object]]]" = OrderedDict()
    for step in steps:
        family = str(step.get("tool_family") or step.get("probe_family") or "")
        if not family:
            continue
        families.setdefault(family, []).append(step)
    rows: list[dict[str, object]] = []
    for family, family_steps in families.items():
        if len(family_steps) <= 1:
            continue
        rows.append(
            {
                "family": family,
                "count": len(family_steps),
                "step_indexes": [step.get("index") for step in family_steps],
                "basis": [_step_citation(step) for step in family_steps[:3]],
            }
        )
    return rows


def _possible_first_patch_opportunities(
    *,
    codex_steps: Sequence[Mapping[str, object]],
    mew_steps: Sequence[Mapping[str, object]],
    codex_summary: Mapping[str, object],
    mew_summary: Mapping[str, object],
    repeated_mew: Mapping[str, object],
) -> list[dict[str, object]]:
    diagnostics: list[dict[str, object]] = []
    codex_first_mutation = _first_step(codex_steps, lambda step: step.get("intent") == "mutation")
    codex_probe_count = _int_or_none(codex_summary.get("probe_count_before_first_mutation"))
    mew_probe_count = _int_or_none(mew_summary.get("probe_count_before_first_mutation"))
    mew_first_mutation = _first_step(mew_steps, lambda step: step.get("intent") == "mutation")
    if codex_first_mutation is not None and codex_probe_count is not None and mew_probe_count is not None:
        if mew_first_mutation is None or mew_probe_count > codex_probe_count:
            candidate = _first_mew_probe_after_probe_count(mew_steps, codex_probe_count)
            basis = [_step_citation(codex_first_mutation, agent="codex")]
            if candidate is not None:
                basis.append(_step_citation(candidate, agent="mew"))
            diagnostics.append(
                {
                    "code": "mew_exceeded_codex_prepatch_probe_budget",
                    "kind": "reference_first_mutation_probe_budget_exceeded",
                    "message": (
                        f"Codex reached its first mutation after {codex_probe_count} probe step(s); "
                        f"mew had {mew_probe_count} probe step(s) before its first mutation."
                    ),
                    "basis": basis,
                    "diagnostic_only": True,
                    "not_live_policy": NOT_LIVE_POLICY,
                    "debug_only": True,
                }
            )

    if mew_first_mutation is None and mew_probe_count:
        last_probe = next((step for step in reversed(mew_steps) if step.get("intent") in PROBE_INTENTS), None)
        diagnostics.append(
            {
                "code": "mew_no_detected_mutation_after_probes",
                "kind": "no_detected_mutation_after_probes",
                "message": "mew has no detectable mutation after collected probe evidence.",
                "basis": [_step_citation(last_probe, agent="mew")] if last_probe is not None else [],
                "diagnostic_only": True,
                "not_live_policy": NOT_LIVE_POLICY,
                "debug_only": True,
            }
        )

    for repeat in repeated_mew.get("before_first_mutation") or []:
        if not isinstance(repeat, Mapping):
            continue
        basis = [item for item in repeat.get("basis") or [] if isinstance(item, Mapping)]
        diagnostics.append(
            {
                "code": "mew_repeated_probe_family_before_mutation",
                "kind": "repeated_probe_family_before_first_mutation",
                "message": (
                    f"mew repeated probe family `{repeat.get('family')}` {repeat.get('count')} times "
                    "before the first mutation."
                ),
                "basis": basis,
                "diagnostic_only": True,
                "not_live_policy": NOT_LIVE_POLICY,
                "debug_only": True,
            }
        )

    failed_prewrite = _first_step(
        _steps_before(mew_steps, mew_first_mutation),
        lambda step: step.get("intent") in {"runtime_verifier", "build_attempt"} and _step_failed(step),
    )
    if failed_prewrite is not None:
        diagnostics.append(
            {
                "code": "mew_failed_build_or_runtime_before_mutation",
                "kind": "failed_build_or_runtime_before_mutation",
                "message": "A failed build/runtime step before the first mutation may be a direct patch opportunity.",
                "basis": [_step_citation(failed_prewrite, agent="mew")],
                "diagnostic_only": True,
                "not_live_policy": NOT_LIVE_POLICY,
                "debug_only": True,
            }
        )
    return diagnostics


def _divergence_summary(
    *,
    codex_summary: Mapping[str, object],
    mew_summary: Mapping[str, object],
    repeated_mew: Mapping[str, object],
    opportunities: Sequence[Mapping[str, object]],
) -> list[str]:
    lines: list[str] = []
    codex_probe_count = codex_summary.get("probe_count_before_first_mutation")
    mew_probe_count = mew_summary.get("probe_count_before_first_mutation")
    lines.append(
        "First mutation: "
        f"Codex step {_summary_value(codex_summary.get('first_mutation_step_index'))} "
        f"after {_summary_value(codex_probe_count)} probe(s); "
        f"mew step {_summary_value(mew_summary.get('first_mutation_step_index'))} "
        f"after {_summary_value(mew_probe_count)} probe(s)."
    )
    lines.append(
        "First verifier: "
        f"Codex step {_summary_value(codex_summary.get('first_verifier_step_index'))}; "
        f"mew step {_summary_value(mew_summary.get('first_verifier_step_index'))}."
    )
    repeated_before = [item for item in repeated_mew.get("before_first_mutation") or [] if isinstance(item, Mapping)]
    if repeated_before:
        families = ", ".join(str(item.get("family") or "") for item in repeated_before[:3])
        lines.append(f"mew repeated probe families before first mutation: {families}.")
    if opportunities:
        lines.append(f"Possible first-patch opportunity diagnostics: {len(opportunities)}.")
    return lines


def _resolve_normalized_trace_dir(root: Path, *, expected_agent: str) -> Path | None:
    candidates = []
    if (root / "summary.json").is_file() or (root / "agent_trace.jsonl").is_file() or (root / "agent_trace.json").is_file():
        candidates.append(root)
    if (root / "normalized-trace").is_dir():
        candidates.append(root / "normalized-trace")
    if root.is_dir():
        candidates.extend(path.parent for path in sorted(root.rglob("normalized-trace/summary.json")))
        candidates.extend(path.parent for path in sorted(root.rglob("agent_trace.jsonl")) if path.parent.name == "normalized-trace")
        candidates.extend(path.parent for path in sorted(root.rglob("agent_trace.json")) if path.parent.name == "normalized-trace")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        summary = _load_json_mapping(candidate / "summary.json")
        if not summary or str(summary.get("agent") or "").casefold() in {"", expected_agent}:
            return candidate
    return None


def _resolve_trace_event_path(trace_dir: Path) -> Path | None:
    for primary in (trace_dir / "agent_trace.jsonl", trace_dir / "agent_trace.json"):
        if primary.is_file():
            return primary
    jsonl_paths = sorted(trace_dir.glob("*.jsonl"))
    if jsonl_paths:
        return jsonl_paths[0]
    json_paths = sorted(path for path in trace_dir.glob("*.json") if path.name != "summary.json")
    return json_paths[0] if json_paths else None


def _resolve_first_existing(root: Path, *, relative_candidates: Sequence[str], basename: str) -> Path | None:
    for relative in relative_candidates:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    if root.is_file() and root.name == basename:
        return root
    if root.is_dir():
        matches = sorted(root.rglob(basename))
        if matches:
            return matches[0]
    return None


def _resolve_manifest_path(root: Path, transcript_path: Path) -> Path | None:
    candidates = (
        transcript_path.parent / "proof-manifest.json",
        root / "proof-manifest.json",
        root / "implement_v2" / "proof-manifest.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if root.is_dir():
        matches = sorted(root.rglob("proof-manifest.json"))
        if matches:
            return matches[0]
    return None


def _report_metrics(report_path: Path | None) -> dict[str, Any]:
    if report_path is None:
        return {}
    report = _load_json_mapping(report_path)
    work_report = report.get("work_report") if isinstance(report.get("work_report"), Mapping) else {}
    result = work_report.get("implement_lane_result") if isinstance(work_report.get("implement_lane_result"), Mapping) else {}
    metrics = result.get("metrics") if isinstance(result.get("metrics"), Mapping) else {}
    return dict(metrics)


def _compact_transcript_metrics(metrics: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "item_count",
        "call_count",
        "output_count",
        "non_tool_count",
        "pairing_valid",
        "pairing_error_count",
        "provider_native_tool_loop",
        "model_json_main_path_detected",
        "transport_kind",
        "native_transport_kind",
    )
    return {key: metrics.get(key) for key in keys if key in metrics}


def _native_provider_request_summary(payload: object) -> dict[str, object]:
    if isinstance(payload, list):
        return {"request_count": len(payload)}
    if not isinstance(payload, Mapping):
        return {}
    requests = payload.get("requests")
    request_count = payload.get("request_count")
    if not isinstance(request_count, int) and isinstance(requests, list):
        request_count = len(requests)
    return {
        "status": payload.get("status"),
        "request_count": request_count,
        "native_transport_kind": payload.get("native_transport_kind"),
        "model_json_main_path_detected": payload.get("model_json_main_path_detected"),
    }


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, Mapping):
            rows.append(dict(payload))
    return rows


def _trace_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return _jsonl_rows(path)
    payload = _load_json_any(path)
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        events = payload.get("events")
        if isinstance(events, list):
            return [dict(item) for item in events if isinstance(item, Mapping)]
    return []


def _load_json_any(path: Path | None) -> object:
    if path is None or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_json_mapping(path: Path | None) -> dict[str, Any]:
    payload = _load_json_any(path)
    return dict(payload) if isinstance(payload, Mapping) else {}


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _json_safe_mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _step_text(step: Mapping[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("tool", "summary", "status"):
        if step.get(key):
            chunks.append(str(step.get(key)))
    arguments = step.get("arguments") if isinstance(step.get("arguments"), Mapping) else {}
    for key in ("cmd", "command", "path", "query", "pattern", "input"):
        if arguments.get(key):
            chunks.append(str(arguments.get(key)))
    return "\n".join(chunks).casefold()


def _command_text(step: Mapping[str, Any]) -> str:
    arguments = step.get("arguments") if isinstance(step.get("arguments"), Mapping) else {}
    for key in ("cmd", "command"):
        value = arguments.get(key)
        if value:
            return str(value)
    tool = str(step.get("tool") or "").casefold()
    if tool in {"command_execution", "exec_command", "run_command", "run_tests", "bash"}:
        return str(step.get("summary") or "")
    return ""


def _extract_step_target(step: Mapping[str, object]) -> str:
    arguments = step.get("arguments") if isinstance(step.get("arguments"), Mapping) else {}
    for key in ("path", "file_path", "query", "pattern"):
        value = arguments.get(key)
        if value:
            return _truncate(str(value), 120)
    summary = str(step.get("summary") or "")
    return _truncate(summary, 120)


def _extract_step_targets(step: Mapping[str, object]) -> list[str]:
    target = _extract_step_target(step)
    return [target] if target else []


def _command_verb(command: str) -> str:
    command = command.strip()
    if not command:
        return ""
    match = re.search(r"(?:^|\s)(rg|grep|git\s+grep|find|fd|ls|tree|cat|sed|head|tail|nl|file|strings|readelf|nm|objdump|xxd|hexdump)\b", command)
    if match:
        return re.sub(r"\s+", "_", match.group(1))
    return command.split()[0].rsplit("/", 1)[-1]


def _regex_basis(text: str, pattern: str) -> str:
    if not text:
        return ""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else ""


def _event_has_source_mutation(event: Mapping[str, Any]) -> bool:
    mutation = event.get("source_mutation")
    if isinstance(mutation, Mapping):
        changed_count = mutation.get("changed_count")
        try:
            if int(changed_count) > 0:
                return True
        except (TypeError, ValueError):
            pass
        if mutation.get("changed_paths") or mutation.get("mutation_refs"):
            return True
    kinds = event.get("source_mutation_effect_kinds") or event.get("side_effect_kinds")
    return isinstance(kinds, list) and bool({"file_write", "source_tree_mutation"} & {str(kind) for kind in kinds})


def _first_step(
    steps: Sequence[Mapping[str, object]],
    predicate: object,
) -> Mapping[str, object] | None:
    for step in steps:
        if callable(predicate) and predicate(step):
            return step
    return None


def _steps_before(
    steps: Sequence[Mapping[str, object]],
    boundary: Mapping[str, object] | None,
) -> list[Mapping[str, object]]:
    if boundary is None:
        return list(steps)
    boundary_index = _int_or_none(boundary.get("index"))
    if boundary_index is None:
        return list(steps)
    return [step for step in steps if (_int_or_none(step.get("index")) or 0) < boundary_index]


def _first_mew_probe_after_probe_count(
    steps: Sequence[Mapping[str, object]],
    probe_count: int,
) -> Mapping[str, object] | None:
    seen = 0
    for step in steps:
        if step.get("intent") not in PROBE_INTENTS:
            continue
        seen += 1
        if seen > probe_count:
            return step
    return None


def _step_failed(step: Mapping[str, object]) -> bool:
    exit_code = step.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return True
    status = str(step.get("status") or "").casefold()
    return status in {"failed", "error", "denied", "invalid", "synthetic_error", "blocked"}


def _step_citation(step: Mapping[str, object] | None, *, agent: str = "") -> dict[str, object]:
    if step is None:
        return {}
    return {
        "agent": agent or step.get("agent") or "",
        "step_index": step.get("index"),
        "turn": step.get("turn"),
        "tool": step.get("tool") or "",
        "tool_id": step.get("tool_id") or "",
        "intent": step.get("intent") or "",
        "summary": step.get("summary") or "",
        "basis": list(step.get("classification_basis") or []),
    }


def _seconds_from_ms(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value) / 1000.0, 3)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def _summary_value(value: object) -> str:
    return "none" if value is None else str(value)


def _summary_cell(value: object) -> str:
    return _markdown_escape(_summary_value(value))


def _markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _append_step_table(lines: list[str], steps: object) -> None:
    rows = [step for step in steps if isinstance(step, Mapping)] if isinstance(steps, list) else []
    if not rows:
        lines.append("No tool steps found.")
        return
    lines.extend(["| # | Turn | Intent | Tool | Status | Elapsed | Summary |", "|---:|---:|---|---|---|---:|---|"])
    for step in rows:
        elapsed = step.get("elapsed_seconds")
        lines.append(
            f"| {_summary_cell(step.get('index'))} | {_summary_cell(step.get('turn'))} | "
            f"`{_markdown_escape(str(step.get('intent') or ''))}` | "
            f"`{_markdown_escape(str(step.get('tool') or ''))}` | "
            f"{_markdown_escape(str(step.get('status') or ''))} | "
            f"{_summary_cell(elapsed)} | "
            f"{_markdown_escape(_truncate(str(step.get('summary') or ''), 140))} |"
        )


__all__ = [
    "HOT_PATH_STEP_DIFF_SCHEMA_VERSION",
    "INTENT_CATEGORIES",
    "analyze_hot_path_step_diff",
    "format_hot_path_step_diff_markdown",
    "write_hot_path_step_diff_report",
]
