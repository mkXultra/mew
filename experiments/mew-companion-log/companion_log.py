#!/usr/bin/env python3
"""Render markdown companion surfaces from a mew session fixture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def render_report(session: dict[str, Any]) -> str:
    """Return a compact markdown companion report for a session fixture."""
    title = session.get("title") or session.get("id") or "Untitled session"
    status = session.get("status", "unknown")
    goal = session.get("goal", "")
    highlights = _as_list(session.get("highlights"))
    next_steps = _as_list(session.get("next_steps"))

    lines = [f"# Companion Log: {title}", "", f"- Status: {status}"]
    if goal:
        lines.append(f"- Goal: {goal}")

    if highlights:
        lines.extend(["", "## Highlights"])
        lines.extend(f"- {item}" for item in highlights)

    if next_steps:
        lines.extend(["", "## Next Steps"])
        lines.extend(f"- {item}" for item in next_steps)

    lines.append("")
    return "\n".join(lines)


def render_morning_journal(session: dict[str, Any]) -> str:
    """Return a fixture-driven morning journal markdown surface."""
    journal = session.get("morning_journal", {})
    if journal is None:
        journal = {}
    if not isinstance(journal, dict):
        raise ValueError("morning_journal must be an object when provided")

    title = journal.get("title") or f"Morning Journal: {session.get('title') or session.get('id') or 'Untitled session'}"
    date = journal.get("date")
    intention = journal.get("intention")
    gratitude = _as_list(journal.get("gratitude"))
    focus = _as_list(journal.get("focus"))
    blockers = _as_list(journal.get("blockers"))
    closing_prompt = journal.get("closing_prompt")

    lines = [f"# {title}"]
    if date:
        lines.extend(["", f"_Date: {date}_"])
    if intention:
        lines.extend(["", "## Intention", str(intention)])
    if gratitude:
        lines.extend(["", "## Gratitude"])
        lines.extend(f"- {item}" for item in gratitude)
    if focus:
        lines.extend(["", "## Focus"])
        lines.extend(f"- {item}" for item in focus)
    if blockers:
        lines.extend(["", "## Watch For"])
        lines.extend(f"- {item}" for item in blockers)
    if closing_prompt:
        lines.extend(["", "## Companion Prompt", str(closing_prompt)])

    lines.append("")
    return "\n".join(lines)


def render_evening_journal(session: dict[str, Any]) -> str:
    """Return a fixture-driven evening journal markdown surface."""
    journal = session.get("evening_journal", {})
    if journal is None:
        journal = {}
    if not isinstance(journal, dict):
        raise ValueError("evening_journal must be an object when provided")

    title = journal.get("title") or f"Evening Journal: {session.get('title') or session.get('id') or 'Untitled session'}"
    date = journal.get("date")
    reflection = journal.get("reflection")
    wins = _as_list(journal.get("wins"))
    learned = _as_list(journal.get("learned"))
    release = _as_list(journal.get("release"))
    tomorrow = _as_list(journal.get("tomorrow"))
    closing_prompt = journal.get("closing_prompt")

    lines = [f"# {title}"]
    if date:
        lines.extend(["", f"_Date: {date}_"])
    if reflection:
        lines.extend(["", "## Reflection", str(reflection)])
    if wins:
        lines.extend(["", "## Wins"])
        lines.extend(f"- {item}" for item in wins)
    if learned:
        lines.extend(["", "## Learned"])
        lines.extend(f"- {item}" for item in learned)
    if release:
        lines.extend(["", "## Release"])
        lines.extend(f"- {item}" for item in release)
    if tomorrow:
        lines.extend(["", "## Tomorrow"])
        lines.extend(f"- {item}" for item in tomorrow)
    if closing_prompt:
        lines.extend(["", "## Companion Prompt", str(closing_prompt)])

    lines.append("")
    return "\n".join(lines)


def render_dream_learning(session: dict[str, Any]) -> str:
    """Return a fixture-driven dream/learning markdown surface."""
    dream_learning = session.get("dream_learning", {})
    if dream_learning is None:
        dream_learning = {}
    if not isinstance(dream_learning, dict):
        raise ValueError("dream_learning must be an object when provided")

    title = dream_learning.get("title") or f"Dream Learning: {session.get('title') or session.get('id') or 'Untitled session'}"
    date = dream_learning.get("date")
    dream = dream_learning.get("dream")
    signals = _as_list(dream_learning.get("signals"))
    learning = _as_list(dream_learning.get("learning"))
    practice = _as_list(dream_learning.get("practice"))
    closing_prompt = dream_learning.get("closing_prompt")

    lines = [f"# {title}"]
    if date:
        lines.extend(["", f"_Date: {date}_"])
    if dream:
        lines.extend(["", "## Dream", str(dream)])
    if signals:
        lines.extend(["", "## Signals"])
        lines.extend(f"- {item}" for item in signals)
    if learning:
        lines.extend(["", "## Learning"])
        lines.extend(f"- {item}" for item in learning)
    if practice:
        lines.extend(["", "## Practice"])
        lines.extend(f"- {item}" for item in practice)
    if closing_prompt:
        lines.extend(["", "## Companion Prompt", str(closing_prompt)])

    lines.append("")
    return "\n".join(lines)


def render_research_digest(data: dict[str, Any]) -> str:
    """Render a deterministic ranked research digest from fixture data."""
    digest = data.get("research_digest", {})
    entries = digest.get("entries", [])
    ranked_entries = sorted(
        entries,
        key=lambda entry: (-int(entry.get("score", 0)), str(entry.get("title", ""))),
    )

    lines = [f"# {digest.get('title', 'Research Digest')}"]
    date = digest.get("date")
    if date:
        lines.extend(["", f"_Date: {date}_"])
    summary = digest.get("summary")
    if summary:
        lines.extend(["", "## Summary", str(summary)])

    lines.extend(["", "## Ranked Entries"])
    for rank, entry in enumerate(ranked_entries, start=1):
        title = entry.get("title", "Untitled research item")
        source = entry.get("source", "unknown source")
        score = entry.get("score", 0)
        lines.append(f"{rank}. **{title}** _({source}, score {score})_")
        reason = entry.get("reason")
        if reason:
            lines.append(f"   - Why: {reason}")
        url = entry.get("url")
        if url:
            lines.append(f"   - URL: {url}")
        tags = entry.get("tags", [])
        if tags:
            lines.append(f"   - Tags: {', '.join(str(tag) for tag in tags)}")

    lines.append("")
    return "\n".join(lines)


def render_state_brief(data: dict[str, Any]) -> str:
    """Render a concise companion brief from a static mew-state-like fixture."""
    state = data.get("current_state", {})
    recent_work = _as_list(data.get("recent_work"))
    risks = _as_list(data.get("unresolved_risks"))
    next_action = data.get("next_side_project_action", {})

    title = state.get("title", "Mew State Companion Brief")
    lines = [f"# {title}"]

    date = data.get("date")
    if date:
        lines.extend(["", f"_Date: {date}_"])

    lines.extend(["", "## Current State"])
    status = state.get("status")
    if status:
        lines.append(f"- Status: {status}")
    summary = state.get("summary")
    if summary:
        lines.append(f"- Summary: {summary}")

    active_task = state.get("active_task")
    if active_task:
        lines.append(f"- Active task: {active_task}")

    lines.extend(["", "## Recent Work"])
    for item in recent_work:
        if isinstance(item, dict):
            label = item.get("label", "Recent item")
            detail = item.get("detail", "")
            lines.append(f"- {label}: {detail}")
        else:
            lines.append(f"- {item}")

    lines.extend(["", "## Unresolved Risks"])
    for risk in risks:
        if isinstance(risk, dict):
            name = risk.get("name", "Risk")
            mitigation = risk.get("mitigation")
            if mitigation:
                lines.append(f"- {name}: {mitigation}")
            else:
                lines.append(f"- {name}")
        else:
            lines.append(f"- {risk}")

    lines.extend(["", "## Next Suggested Side-Project Action"])
    if isinstance(next_action, dict):
        label = next_action.get("label", "Next action")
        reason = next_action.get("reason")
        lines.append(f"- {label}")
        if reason:
            lines.append(f"  - Why: {reason}")
    elif next_action:
        lines.append(f"- {next_action}")

    lines.append("")
    return "\n".join(lines)


def render_bundle(manifest: dict[str, Any], *, base_path: Path) -> str:
    """Render a deterministic companion bundle from a multi-fixture manifest."""
    title = manifest.get("title") or manifest.get("id") or "Companion Bundle"
    entries = _as_list(manifest.get("entries"))

    lines = [f"# Companion Bundle: {title}"]
    date = manifest.get("date")
    if date:
        lines.extend(["", f"_Date: {date}_"])

    current_group: str | None = None
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError("bundle entries must be objects")
        fixture_name = entry.get("fixture")
        if not fixture_name:
            raise ValueError("bundle entries must declare a fixture")
        mode = str(entry.get("mode", "report"))
        if mode == "bundle" or mode not in RENDERERS:
            raise ValueError(f"unsupported bundle entry mode: {mode}")

        fixture_path = Path(str(fixture_name))
        if not fixture_path.is_absolute():
            fixture_path = base_path / fixture_path

        group = str(entry.get("group") or "Companion Entries")
        if group != current_group:
            lines.extend(["", f"## {group}"])
            current_group = group

        label = entry.get("label") or entry.get("surface") or f"Entry {index}"
        surface = entry.get("surface") or mode
        lines.extend(
            [
                "",
                f"### {label}",
                f"- Fixture: {fixture_name}",
                f"- Surface: {surface}",
                "",
                RENDERERS[mode](load_session(fixture_path)).strip(),
            ]
        )

    lines.append("")
    return "\n".join(lines)


def _next_action_label(next_action: Any) -> str:
    if isinstance(next_action, dict):
        return str(next_action.get("label") or "Review archived output")
    if next_action:
        return str(next_action)
    return "Review archived output"


def _next_action_reason(next_action: Any) -> str:
    if isinstance(next_action, dict):
        return str(next_action.get("reason") or "")
    return ""


def render_archive_index(manifest: dict[str, Any]) -> str:
    """Render a deterministic multi-day companion archive index."""
    title = manifest.get("title") or manifest.get("id") or "Companion Archive"
    days = _as_list(manifest.get("days"))

    lines = [f"# Companion Archive Index: {title}"]
    date = manifest.get("date")
    if date:
        lines.extend(["", f"_Date: {date}_"])
    summary = manifest.get("summary")
    if summary:
        lines.extend(["", "## Summary", str(summary)])

    normalized_days: list[tuple[str, str, list[dict[str, Any]]]] = []
    for day_record in days:
        if not isinstance(day_record, dict):
            raise ValueError("archive days must be objects")
        day = str(day_record.get("day") or "")
        if not day:
            raise ValueError("archive days must declare a day")
        entries: list[dict[str, Any]] = []
        for entry in _as_list(day_record.get("entries")):
            if not isinstance(entry, dict):
                raise ValueError("archive entries must be objects")
            if not entry.get("fixture"):
                raise ValueError("archive entries must declare a fixture")
            entries.append(entry)
        normalized_days.append((day, str(day_record.get("summary") or ""), entries))

    for day, day_summary, entries in sorted(normalized_days, key=lambda item: item[0]):
        lines.extend(["", f"## {day}"])
        if day_summary:
            lines.append(f"- Summary: {day_summary}")
        if not entries:
            lines.append("- No companion outputs archived for this day.")
            continue

        current_surface: str | None = None
        current_action: str | None = None
        sorted_entries = sorted(
            entries,
            key=lambda entry: (
                str(entry.get("surface") or entry.get("mode") or "companion-output"),
                _next_action_label(entry.get("next_action")),
                str(entry.get("title") or "Untitled companion output"),
                str(entry.get("fixture") or ""),
            ),
        )
        for entry in sorted_entries:
            surface = str(entry.get("surface") or entry.get("mode") or "companion-output")
            action_label = _next_action_label(entry.get("next_action"))
            if surface != current_surface:
                lines.extend(["", f"### {surface}"])
                current_surface = surface
                current_action = None
            if action_label != current_action:
                lines.append(f"#### Next action: {action_label}")
                current_action = action_label

            title = str(entry.get("title") or "Untitled companion output")
            mode = str(entry.get("mode") or "report")
            entry_summary = str(entry.get("summary") or "")
            bullet = f"- **{title}** (`{mode}`)"
            if entry_summary:
                bullet = f"{bullet} — {entry_summary}"
            lines.append(bullet)
            lines.append(f"  - Fixture: {entry['fixture']}")
            reason = _next_action_reason(entry.get("next_action"))
            if reason:
                lines.append(f"  - Why: {reason}")

    lines.append("")
    return "\n".join(lines)


RENDERERS = {
    "report": render_report,
    "morning-journal": render_morning_journal,
    "evening-journal": render_evening_journal,
    "dream-learning": render_dream_learning,
    "research-digest": render_research_digest,
    "state-brief": render_state_brief,
    "bundle": render_bundle,
    "archive-index": render_archive_index,
}


def load_session(path: Path) -> dict[str, Any]:
    """Load a session fixture from JSON."""
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("fixture JSON must contain an object at the top level")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a markdown companion surface from a fixture JSON file."
    )
    parser.add_argument("fixture", type=Path, help="Path to a fixture JSON file")
    parser.add_argument(
        "--mode",
        choices=sorted(RENDERERS),
        default="report",
        help="Markdown surface to render; defaults to the companion report",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write the markdown output to this file instead of stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    renderer = RENDERERS[args.mode]
    try:
        if args.mode == "bundle":
            report = render_bundle(load_session(args.fixture), base_path=args.fixture.parent)
        else:
            report = renderer(load_session(args.fixture))
    except FileNotFoundError as exc:
        missing = exc.filename or str(exc)
        print(f"error: fixture not found: {missing}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
