from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MAX_ITEMS = 8
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PREFERENCE_STOP_WORDS = {
    "about",
    "and",
    "for",
    "from",
    "interest",
    "interested",
    "like",
    "likes",
    "prefer",
    "prefers",
    "the",
    "with",
}


@dataclass(frozen=True)
class RankedItem:
    item: dict[str, Any]
    score: int
    reasons: list[str]


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value


def resolve_paper_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return validate_date(explicit_date)
    return validate_date(datetime.now().date().isoformat())


def morning_paper_path(output_dir: Path, day: str) -> Path:
    return output_dir / ".mew" / "morning-paper" / f"{day}.md"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_feed(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


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


def preference_keywords(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    if ": " in text:
        text = text.split(": ", 1)[1]
    keywords = [text]
    for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", text):
        if token.casefold() not in PREFERENCE_STOP_WORDS:
            keywords.append(token)
    return unique(keywords, limit=20)


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
    memory = state.get("memory")
    if isinstance(memory, dict):
        deep = memory.get("deep")
        if isinstance(deep, dict):
            interests.extend(string_items(deep.get("interests")))
            for preference in string_items(deep.get("preferences")):
                interests.extend(preference_keywords(preference))
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


def ranked_item_to_dict(ranked_item: RankedItem) -> dict[str, Any]:
    item = ranked_item.item
    return {
        "title": normalize_text(item.get("title")) or "Untitled",
        "source": normalize_text(item.get("source")) or "unknown source",
        "url": normalize_text(item.get("url")),
        "summary": normalize_text(item.get("summary")),
        "tags": item_tags(item),
        "score": ranked_item.score,
        "reasons": list(ranked_item.reasons),
    }


def build_morning_paper_view_model(
    items: list[dict[str, Any]],
    state: dict[str, Any],
    explicit_date: str | None = None,
    explicit_interests: list[str] | None = None,
    limit: int = MAX_ITEMS,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    day = resolve_paper_date(explicit_date)
    interests = collect_interest_tags(state, explicit_interests)
    ranked = [ranked_item_to_dict(item) for item in rank_items(items, interests, limit)]
    return {
        "date": day,
        "interests": interests,
        "items": ranked,
        "top_picks": [item for item in ranked if item["score"] > 0],
        "explore_later": [item for item in ranked if item["score"] <= 0],
    }


def render_item(index: int, item: dict[str, Any]) -> list[str]:
    lines = [f"### {index}. {item['title']}", f"- score: {item['score']}", f"- source: {item['source']}"]
    if item["url"]:
        lines.append(f"- url: {item['url']}")
    if item["tags"]:
        lines.append(f"- tags: {', '.join(item['tags'])}")
    for reason in item["reasons"]:
        lines.append(f"- why: {reason}")
    if item["summary"]:
        lines.extend(["", item["summary"]])
    return lines


def render_morning_paper_markdown(view_model: dict[str, Any]) -> str:
    top_picks = view_model["top_picks"]
    exploration = view_model["explore_later"]
    lines = [
        f"# Mew Morning Paper {view_model['date']}",
        "",
        "## Interests",
    ]
    if view_model["interests"]:
        for interest in view_model["interests"]:
            lines.append(f"- {interest}")
    else:
        lines.append("- No interest tags configured")

    lines.extend(["", "## Top picks"])
    if top_picks:
        for index, item in enumerate(top_picks, start=1):
            lines.extend(["", *render_item(index, item)])
    elif view_model["items"]:
        lines.append("- No direct interest matches")
    else:
        lines.append("- No feed items recorded")

    if exploration:
        lines.extend(["", "## Explore later"])
        for index, item in enumerate(exploration, start=1):
            lines.extend(["", *render_item(index, item)])
    return "\n".join(lines) + "\n"


def format_morning_paper_view(view_model: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Mew morning paper {view_model['date']}",
            f"interests: {', '.join(view_model['interests']) if view_model['interests'] else '-'}",
            f"top_picks: {len(view_model['top_picks'])}",
            f"explore_later: {len(view_model['explore_later'])}",
        ]
    )


def write_morning_paper_report(view_model: dict[str, Any], output_dir: Path) -> Path:
    path = morning_paper_path(output_dir, view_model["date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_morning_paper_markdown(view_model), encoding="utf-8")
    return path
