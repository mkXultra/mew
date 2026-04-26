#!/usr/bin/env python3
"""Render markdown companion surfaces from a mew session fixture."""

from __future__ import annotations

import argparse
import json
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


RENDERERS = {
    "report": render_report,
    "morning-journal": render_morning_journal,
    "evening-journal": render_evening_journal,
    "dream-learning": render_dream_learning,
    "research-digest": render_research_digest,
    "state-brief": render_state_brief,
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
    report = renderer(load_session(args.fixture))
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
