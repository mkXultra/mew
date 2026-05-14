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

INTENT_CATEGORIES = (
    "source_scan",
    "source_read",
    "binary_probe",
    "disassembly_probe",
    "build_attempt",
    "runtime_verifier",
    "mutation",
    "process_poll",
    "finish",
    "other_probe",
)
PROBE_INTENTS = frozenset(
    {
        "source_scan",
        "source_read",
        "binary_probe",
        "disassembly_probe",
        "build_attempt",
        "runtime_verifier",
        "other_probe",
    }
)
MUTATION_TOOLS = frozenset({"apply_patch", "edit_file", "write_file"})
PROCESS_POLL_TOOLS = frozenset({"poll_command", "read_command_output", "write_stdin", "bashoutput"})
SOURCE_READ_TOOLS = frozenset({"read_file"})
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
) -> dict[str, object]:
    """Build a sidecar step-diff report from existing artifact roots."""

    codex = _load_codex_bundle(Path(str(codex_reference_root)).expanduser())
    mew = _load_mew_bundle(Path(str(mew_artifact_root)).expanduser())
    codex_steps = _normalize_tool_steps(codex.events, agent="codex")
    mew_steps = _normalize_tool_steps(mew.events, agent="mew")
    codex_step_summary = _step_summary(codex_steps)
    mew_step_summary = _step_summary(mew_steps)
    repeated_probe_families = {
        "codex": _repeated_probe_families(codex_steps),
        "mew": _repeated_probe_families(mew_steps),
    }
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
    return {
        "schema_version": HOT_PATH_STEP_DIFF_SCHEMA_VERSION,
        "report_kind": "m6_24_hot_path_step_diff",
        "sidecar_only": True,
        "intent_categories": list(INTENT_CATEGORIES),
        "inputs": {
            "codex_reference_root": str(codex.root.resolve(strict=False)),
            "mew_artifact_root": str(mew.root.resolve(strict=False)),
        },
        "sources": {
            "codex": codex.sources,
            "mew": mew.sources,
        },
        "warnings": {
            "codex": list(codex.warnings),
            "mew": list(mew.warnings),
        },
        "summary": {
            "codex": _combined_summary(codex.summary, codex_step_summary, codex.artifact_summary or {}),
            "mew": _combined_summary(mew.summary, mew_step_summary, mew.artifact_summary or {}),
        },
        "normalized_codex_steps": codex_steps,
        "normalized_mew_steps": mew_steps,
        "repeated_probe_family_diagnostics": repeated_probe_families,
        "possible_first_patch_opportunity_diagnostics": possible_first_patch_opportunities,
        "divergence_summary": divergence_summary,
    }


def write_hot_path_step_diff_report(
    *,
    codex_reference_root: object,
    mew_artifact_root: object,
    out_json: object,
    out_md: object,
) -> dict[str, object]:
    """Build and write JSON plus Markdown step-diff reports."""

    report = analyze_hot_path_step_diff(
        codex_reference_root=codex_reference_root,
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
    mew_summary = _mapping(summary.get("mew"))
    lines = [
        "# M6.24 Hot-Path Step Diff",
        "",
        "Artifact-only sidecar analysis. This report does not affect live mew behavior.",
        "",
        "## Inputs",
        "",
        f"- Codex reference root: `{_markdown_escape(str(_mapping(report.get('inputs')).get('codex_reference_root') or ''))}`",
        f"- mew artifact root: `{_markdown_escape(str(_mapping(report.get('inputs')).get('mew_artifact_root') or ''))}`",
        "",
        "## Summary",
        "",
        "| Metric | Codex reference | mew artifact |",
        "|---|---:|---:|",
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
        lines.append(f"| {label} | {_summary_cell(codex_summary.get(key))} | {_summary_cell(mew_summary.get(key))} |")

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
    for agent in ("codex", "mew"):
        diagnostics = _mapping(_mapping(report.get("repeated_probe_family_diagnostics")).get(agent))
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

    lines.extend(["## Normalized Codex Steps", ""])
    _append_step_table(lines, report.get("normalized_codex_steps") or [])
    lines.extend(["", "## Normalized mew Steps", ""])
    _append_step_table(lines, report.get("normalized_mew_steps") or [])
    return "\n".join(lines)


def _load_codex_bundle(root: Path) -> TraceBundle:
    warnings: list[str] = []
    trace_dir = _resolve_normalized_trace_dir(root, expected_agent="codex")
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
            events, generated_summary = normalize_harbor_agent_trace(agent="codex", task_dir=root)
            summary = summary or generated_summary
            sources["fallback_task_dir"] = str(root.resolve(strict=False))
        except Exception as exc:  # noqa: BLE001 - artifact reader should degrade with warnings.
            warnings.append(f"could not normalize codex task dir fallback: {exc}")
    if not summary:
        summary = summarize_trace(agent="codex", events=events)
    if not events:
        warnings.append("no codex events were found")
    return TraceBundle(agent="codex", root=root, events=tuple(events), summary=summary, sources=sources, warnings=tuple(warnings))


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
        merged = _merge_step_events(started, completed)
        intent, basis = _classify_intent(merged)
        family = _probe_family(merged, intent=intent)
        step = {
            "index": step_index,
            "agent": agent,
            "turn": _int_or_none(merged.get("step_id")),
            "sequence": _int_or_none(merged.get("sequence_index")),
            "tool": str(merged.get("tool") or ""),
            "tool_id": str(merged.get("id") or ""),
            "intent": intent,
            "probe_family": family,
            "summary": _truncate(str(merged.get("summary") or ""), 500),
            "command": _truncate(_command_text(merged), 500),
            "status": str(merged.get("status") or ""),
            "exit_code": merged.get("exit_code") if isinstance(merged.get("exit_code"), int) else None,
            "elapsed_seconds": _seconds_from_ms(merged.get("elapsed_ms")),
            "duration_seconds": _seconds_from_ms(merged.get("duration_ms")),
            "source": str(merged.get("source") or ""),
            "line_number": _int_or_none(merged.get("line_number")),
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


def _classify_intent(step: Mapping[str, Any]) -> tuple[str, list[str]]:
    tool = str(step.get("tool") or "").casefold()
    text = _step_text(step)
    command = _command_text(step).casefold()
    arguments = step.get("arguments") if isinstance(step.get("arguments"), Mapping) else {}
    contract = step.get("execution_contract") if isinstance(step.get("execution_contract"), Mapping) else {}

    if tool in {"finish", "finish_call"}:
        return "finish", [f"tool={tool}"]
    if tool in MUTATION_TOOLS:
        return "mutation", [f"tool={tool}"]
    if _event_has_source_mutation(step):
        return "mutation", ["mutation tool or source_mutation sidecar", "source_mutation_detected"]
    if _command_has_write_pattern(command):
        return "mutation", ["command_write_pattern"]
    if tool in PROCESS_POLL_TOOLS:
        return "process_poll", [f"tool={tool}"]
    if _looks_like_process_poll(command):
        return "process_poll", ["command_process_poll_pattern"]

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
        family = str(step.get("probe_family") or "")
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
