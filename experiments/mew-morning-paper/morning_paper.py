from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_ITEMS = 8


@dataclass
class RankedItem:
    item: dict[str, Any]
    score: int
    reasons: list[str]


@dataclass
class OutputPaths:
    morning_paper: Path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_feed(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def resolve_date(state: dict[str, Any], explicit_date: str | None = None) -> str:
    if explicit_date:
        return explicit_date
    for key in ("date", "today", "current_date"):
        value = state.get(key)
        if isinstance(value, str) and value:
            return value
    return datetime.now().date().isoformat()


def build_paths(base_dir: Path, day: str) -> OutputPaths:
    return OutputPaths(morning_paper=base_dir / ".mew" / "morning-paper" / f"{day}.md")


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def normalize_tag(value: Any) -> str:
    return normalize_text(value).casefold()


def string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = normalize_text(item)
        if text:
            items.append(text)
    return items


def unique(items: list[str], limit: int = MAX_ITEMS) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = normalize_text(item)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def collect_interest_tags(state: dict[str, Any], explicit_interests: list[str] | None = None) -> list[str]:
    interests = []
    interests.extend(string_items(explicit_interests or []))
    for key in ("interests", "interest_tags"):
        interests.extend(string_items(state.get(key)))
    preferences = state.get("preferences")
    if isinstance(preferences, dict):
        interests.extend(string_items(preferences.get("interests")))
        interests.extend(string_items(preferences.get("tags")))
    profile = state.get("profile")
    if isinstance(profile, dict):
        interests.extend(string_items(profile.get("interests")))
    return unique(interests)


def item_tags(item: dict[str, Any]) -> list[str]:
    tags = []
    for key in ("tags", "topics"):
        tags.extend(string_items(item.get(key)))
    return unique(tags, limit=20)


def searchable_text(item: dict[str, Any]) -> str:
    parts = [
        normalize_text(item.get("title")),
        normalize_text(item.get("summary")),
        normalize_text(item.get("source")),
    ]
    parts.extend(item_tags(item))
    return " ".join(part for part in parts if part).casefold()


def interest_matches_text(interest: str, text: str) -> bool:
    normalized = normalize_tag(interest)
    if not normalized:
        return False
    if " " in normalized or "-" in normalized:
        return normalized in text
    return re.search(rf"\b{re.escape(normalized)}\b", text) is not None


def score_item(item: dict[str, Any], interests: list[str]) -> RankedItem:
    score = 0
    reasons = []
    tags = {normalize_tag(tag) for tag in item_tags(item)}
    text = searchable_text(item)

    if not interests:
        return RankedItem(item=item, score=0, reasons=["No interest tags configured; kept for exploration"])

    for interest in interests:
        normalized = normalize_tag(interest)
        if not normalized:
            continue
        if normalized in tags:
            score += 10
            reasons.append(f"matched tag `{interest}`")
        elif interest_matches_text(interest, text):
            score += 4
            reasons.append(f"mentioned `{interest}`")

    if score == 0:
        reasons.append("No direct interest match; kept as low-priority exploration")
    return RankedItem(item=item, score=score, reasons=unique(reasons, limit=4))


def rank_items(items: list[dict[str, Any]], interests: list[str], limit: int = MAX_ITEMS) -> list[RankedItem]:
    ranked = [score_item(item, interests) for item in items]
    ranked.sort(key=lambda ranked_item: (-ranked_item.score, normalize_text(ranked_item.item.get("title")).casefold()))
    return ranked[:limit]


def render_item(index: int, ranked_item: RankedItem) -> list[str]:
    item = ranked_item.item
    title = normalize_text(item.get("title")) or "Untitled"
    source = normalize_text(item.get("source")) or "unknown source"
    url = normalize_text(item.get("url"))
    summary = normalize_text(item.get("summary"))
    tags = item_tags(item)

    lines = [f"### {index}. {title}", f"- score: {ranked_item.score}", f"- source: {source}"]
    if url:
        lines.append(f"- url: {url}")
    if tags:
        lines.append(f"- tags: {', '.join(tags)}")
    for reason in ranked_item.reasons:
        lines.append(f"- why: {reason}")
    if summary:
        lines.extend(["", summary])
    return lines


def render_morning_paper(day: str, items: list[dict[str, Any]], interests: list[str], limit: int = MAX_ITEMS) -> str:
    ranked = rank_items(items, interests, limit)
    top_picks = [item for item in ranked if item.score > 0]
    exploration = [item for item in ranked if item.score <= 0]
    lines = [
        f"# Mew Morning Paper {day}",
        "",
        "## Interests",
    ]
    if interests:
        for interest in interests:
            lines.append(f"- {interest}")
    else:
        lines.append("- No interest tags configured")

    lines.extend(["", "## Top picks"])
    if top_picks:
        for index, ranked_item in enumerate(top_picks, start=1):
            lines.extend(["", *render_item(index, ranked_item)])
    elif ranked:
        lines.append("- No direct interest matches")
    else:
        lines.append("- No feed items recorded")

    if exploration:
        lines.extend(["", "## Explore later"])
        for index, ranked_item in enumerate(exploration, start=1):
            lines.extend(["", *render_item(index, ranked_item)])
    return "\n".join(lines) + "\n"


def write_outputs(paths: OutputPaths, text: str) -> None:
    paths.morning_paper.parent.mkdir(parents=True, exist_ok=True)
    paths.morning_paper.write_text(text, encoding="utf-8")


def generate(
    feed_path: Path,
    output_dir: Path,
    state_path: Path | None = None,
    explicit_date: str | None = None,
    explicit_interests: list[str] | None = None,
    limit: int = MAX_ITEMS,
) -> OutputPaths:
    state = load_state(state_path)
    items = load_feed(feed_path)
    interests = collect_interest_tags(state, explicit_interests)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, render_morning_paper(day, items, interests, limit))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a mew morning paper from static feed JSON")
    parser.add_argument("feed_path", type=Path)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    parser.add_argument("--interest", action="append", default=[])
    parser.add_argument("--limit", type=int, default=MAX_ITEMS)
    args = parser.parse_args(argv)

    paths = generate(
        args.feed_path,
        args.output_dir,
        state_path=args.state_path,
        explicit_date=args.date,
        explicit_interests=args.interest,
        limit=args.limit,
    )
    print(paths.morning_paper)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
